from email.utils import formataddr
import json
import logging
import re
from google.appengine.api import mail

from google.appengine.ext import ndb
from google.appengine.ext.webapp.blobstore_handlers import BlobstoreDownloadHandler
import os
from webapp2 import RequestHandler, Route, WSGIApplication, cached_property
from webapp2_extras import sessions
from model import Account


def json_response(func):
    def wrapper(self, *args, **kwargs):
        result = func(self, *args, **kwargs)
        if isinstance(result, tuple):
            code, response = result
        else:
            code, response = 200, result
        self.response.status_int = code
        self.response.content_type = 'application/json'
        self.response.charset = 'utf8'
        self.response.out.write(json.dumps(response))
    return wrapper


class SessionAwareHandlerMixin(object):

    def dispatch(self):
        self.session_store = sessions.get_store(request=self.request)
        try:
            super(SessionAwareHandlerMixin, self).dispatch()
        finally:
            self.session_store.save_sessions(self.response)

    @cached_property
    def session(self):
        return self.session_store.get_session(backend='memcache')

    def get_account(self):
        account_id = self.session.get('account_id')
        if account_id:
            account = Account.get_by_id(account_id)
            if account and account.is_valid:
                return account

    def create_account(self):
        account = Account.create()
        self.session['account_id'] = account.key.id()
        return account


class InitHandler(SessionAwareHandlerMixin, RequestHandler):

    @json_response
    def get(self):
        account = self.get_account()
        if account:
            logging.info("Account already exists: %s" % account.email)
        else:
            account = self.create_account()
        return {
            'account': account.api_repr()
        }


class InboxHandler(SessionAwareHandlerMixin, RequestHandler):

    @json_response
    def get(self):
        account = self.get_account()
        if account:
            return {
                'account': account.api_repr(),
                'messages': [message.api_repr() for message in account.messages]
            }
        else:
            self.abort(410)


class ExtendTimeHandler(SessionAwareHandlerMixin, RequestHandler):

    @json_response
    def get(self):
        account = self.get_account()
        if account and account.is_valid:
            account.extend_validity()
            return {
                'account': account.api_repr()
            }
        else:
            self.abort(403)


class NewAccountHandler(SessionAwareHandlerMixin, RequestHandler):

    @json_response
    def get(self):
        account = self.get_account()
        if account:
            account.close()
        account = self.create_account()
        return {
            'account': account.api_repr()
        }


class MessageHandler(SessionAwareHandlerMixin, RequestHandler):

    @json_response
    def get(self, key):
        try:
            message_key = ndb.Key(urlsafe=key)
            message = message_key.get()
        except Exception as e:
            logging.exception(e)
            self.abort(404)
        else:
            account = self.get_account()
            message_account_key = message_key.parent()
            if not account or account.key != message_account_key:
                self.abort(403)
            else:
                if not message.read:
                    message.read = True
                    message.put()
                return {
                    'message': message.api_repr(full=True)
                }


class AttachmentDownloadHandler(SessionAwareHandlerMixin, BlobstoreDownloadHandler):

    def get(self, key):
        try:
            attachment_key = ndb.Key(urlsafe=key)
            attachment = attachment_key.get()
        except Exception as e:
            logging.exception(e)
            self.abort(404)
        else:
            account = self.get_account()
            attachment_account_key = attachment_key.parent().parent()
            if not account or account.key != attachment_account_key:
                self.abort(403)
            else:
                self.send_blob(attachment.blobkey, save_as=attachment.filename)


def is_email_valid(email_address):
    return bool(re.match(r'[^@]+@[^@]+\.[^@]+$', email_address))


class ForwardMessageHandler(SessionAwareHandlerMixin, RequestHandler):

    @json_response
    def post(self, key):
        email_address = self.request.get('address').strip()
        if not is_email_valid(email_address):
            return 400, {
                'error': 'Email address is not valid.'
            }
        try:
            message_key = ndb.Key(urlsafe=key)
            message = message_key.get()
        except Exception as e:
            logging.exception(e)
            self.abort(404)
        else:
            account = self.get_account()
            message_account_key = message_key.parent()
            if not account or account.key != message_account_key:
                self.abort(403)
            else:
                logging.info('Forwarding message from %s to %s' % (account.email, email_address))
                email_message = mail.EmailMessage(
                    sender=formataddr((message.sender_name, account.email)),
                    to=formataddr((message.receiver_name, email_address)),
                    reply_to=message.reply_to or message.sender_address,
                    subject=message.subject or '',
                    body=message.body,
                    html=message.html,
                )
                email_message.send()


config = {
    'webapp2_extras.sessions': {
        'secret_key': os.environ['SESSION_SECRET_KEY'],
    },
}

app = WSGIApplication([
    Route('/account/init', InitHandler),
    Route('/account/inbox', InboxHandler),
    Route('/account/extend', ExtendTimeHandler),
    Route('/account/new', NewAccountHandler),
    Route('/message/<key>', MessageHandler),
    Route('/message/<key>/forward', ForwardMessageHandler),
    Route('/attachment/<key>', AttachmentDownloadHandler),
], config=config, debug=True)
