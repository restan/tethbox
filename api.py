from datetime import datetime
import json
import logging

from google.appengine.ext import ndb
from google.appengine.ext.webapp import blobstore_handlers
import os
import webapp2
from webapp2_extras import sessions
from model import Account


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
        account = self.get_account()
        if account:
            logging.info("Account already exists: %s" % account.email)
        else:
            account = self.create_account()
        return {
            'account': account.api_repr()
        }


class InboxHandler(JsonHandler):

    def get_json(self):
        account = self.get_account()
        if account:
            return {
                'account': account.api_repr(),
                'messages': [message.api_repr() for message in account.messages]
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


class NewAccountHandler(JsonHandler):

    def get_json(self):
        account = self.get_account()
        if account:
            account.close()
        account = self.create_account()
        return {
            'account': account.api_repr()
        }


class ResetTimerHandler(JsonHandler):

    def get_json(self):
        account = self.get_account()
        if account and account.is_valid:
            account.extend_validity()
            return {
                'account': account.api_repr()
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
            account = self.get_account()
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
