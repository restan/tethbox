from datetime import datetime
import json
import logging

from google.appengine.ext import ndb
from google.appengine.ext.webapp import blobstore_handlers
import os
import webapp2
from webapp2_extras import sessions

from tethbox.model import Account, Message, Attachment


EPOCH = datetime(1970, 1, 1)


def to_timestamp(datetime_):
    return int((datetime_ - EPOCH).total_seconds())


def get_account(session):
    account_id = session.get('account_id')
    if account_id:
        account = Account.get_by_id(account_id)
        if account and account.is_valid:
            return account


def create_account(session):
    account = Account.create()
    session['account_id'] = account.key.id()
    return account


def account_to_dict(account):
    return {
        'email': account.email,
        'expireIn': account.expire_in
    }


def message_to_dict(message, short=True):
    result = {
        'key': message.key.urlsafe(),
        'sender_name': message.sender_name,
        'sender_address': message.sender_address,
        'date': to_timestamp(message.date),
        'subject': message.subject,
        'read': message.read
    }
    if not short:
        result['html'] = message.html
        attachments = Attachment.query(ancestor=message.key)
        result['attachments'] = [attachment_to_dict(attachment) for attachment in attachments]
    return result


def attachment_to_dict(attachment):
    return {
        'key': attachment.key.urlsafe(),
        'filename': attachment.filename,
        'size': attachment.size
    }


class SessionAwareHandlerMixin(object):

    def dispatch(self):
        self.session_store = sessions.get_store(request=self.request)
        try:
            super(SessionAwareHandlerMixin, self).dispatch()
        finally:
            self.session_store.save_sessions(self.response)

    @webapp2.cached_property
    def session(self):
        return self.session_store.get_session(backend='memcache')


class JsonHandler(SessionAwareHandlerMixin, webapp2.RequestHandler):

    def get(self, *args, **kwargs):
        response = self.get_json(*args, **kwargs)
        self.response.content_type = 'application/json'
        self.response.charset = 'utf8'
        self.response.out.write(json.dumps(response))

    def get_json(self, *args, **kwargs):
        raise NotImplementedError()


class InitHandler(JsonHandler):

    def get_json(self):
        account = get_account(self.session)
        if account:
            logging.info("Account already exists: %s" % account.email)
        else:
            account = create_account(self.session)
        return {
            'account': account_to_dict(account)
        }


class InboxHandler(JsonHandler):

    def get_json(self):
        account = get_account(self.session)
        if account:
            messages = Message.query(ancestor=account.key).order(Message.date)
            return {
                'account': account_to_dict(account),
                'messages': [
                    message_to_dict(message) for message in messages
                ]
            }
        else:
            self.abort(410)


class MessageHandler(JsonHandler):

    def get_json(self, key):
        try:
            message_key = ndb.Key(urlsafe=key)
            message = message_key.get()
        except Exception as e:
            logging.exception(e)
            self.abort(404)
        else:
            account = get_account(self.session)
            message_account_key = message_key.parent()
            if not account or account.key != message_account_key:
                self.abort(403)
            else:
                if not message.read:
                    message.read = True
                    message.put()
                return {
                    'message': message_to_dict(message, short=False)
                }


class NewAccountHandler(JsonHandler):

    def get_json(self):
        account = get_account(self.session)
        if account:
            account.close()
        account = create_account(self.session)
        return {
            'account': account_to_dict(account)
        }


class ResetTimerHandler(JsonHandler):

    def get_json(self):
        account = get_account(self.session)
        if account and account.is_valid:
            account.extend_validity()
            return {
                'account': account_to_dict(account)
            }
        else:
            self.abort(403)


class AttachmentHandler(SessionAwareHandlerMixin, blobstore_handlers.BlobstoreDownloadHandler):

    def get(self, key):
        try:
            attachment_key = ndb.Key(urlsafe=key)
            attachment = attachment_key.get()
        except Exception as e:
            logging.exception(e)
            self.abort(404)
        else:
            account = get_account(self.session)
            attachment_account_key = attachment_key.parent().parent()
            if not account or account.key != attachment_account_key:
                self.abort(403)
            else:
                self.send_blob(attachment.blobkey, save_as=attachment.filename)


config = {
    'webapp2_extras.sessions': {
        'secret_key': os.environ['SESSION_SECRET_KEY'],
    },
}

app = webapp2.WSGIApplication([
    webapp2.Route('/init', InitHandler),
    webapp2.Route('/inbox', InboxHandler),
    webapp2.Route('/message/<key>', MessageHandler),
    webapp2.Route('/newAccount', NewAccountHandler),
    webapp2.Route('/resetTimer', ResetTimerHandler),
    webapp2.Route('/attachment/<key>', AttachmentHandler),
], config=config, debug=True)
