from datetime import datetime, timedelta
import json
import logging
from random import randint
import string

from google.appengine.api import app_identity
from google.appengine.ext import ndb
import webapp2
from webapp2_extras import sessions

from tethbox.model import Account, Message


BASE62_DIGITS = string.digits + string.letters
BASE62_SIZE = len(BASE62_DIGITS)
EPOCH = datetime(1970, 1, 1)


def base62_encode(number):
    result = ''
    while number > 0:
        result = BASE62_DIGITS[number%BASE62_SIZE] + result
        number /= BASE62_SIZE
    return result

def to_timestamp(datetime_):
    return int((datetime_ - EPOCH).total_seconds())


class BaseHandler(webapp2.RequestHandler):
    def dispatch(self):
        self.session_store = sessions.get_store(request=self.request)
        try:
            webapp2.RequestHandler.dispatch(self)
        finally:
            self.session_store.save_sessions(self.response)

    @webapp2.cached_property
    def session(self):
        return self.session_store.get_session(backend='memcache')

    def _get_account(self):
        account_id = self.session.get('account_id')
        if account_id:
            account = Account.get_by_id(account_id)
            if account and account.is_valid:
                return account

    def _create_account(self):
        account = Account(
            email=self._create_unique_email_address(),
            valid_until=datetime.now()+timedelta(seconds=600)
        )
        account.put()
        self.session['account_id'] = account.key.id()
        return account

    def _create_unique_email_address(self):
        _, number = Account.allocate_ids(1)
        user = base62_encode(number)
        return '%s@%s.appspot.com' % (user, app_identity.get_application_id())


class InitHandler(BaseHandler):

    def get(self):
        account = self._get_account()
        if account:
            logging.info("Account already exists: %s" % account.email)
        else:
            account = self._create_account()
            logging.info("Account created: %s" % account.email)
        response = {
            'account': {
                'email': account.email,
                'expireIn': account.expire_in
            }
        }
        self.response.content_type = 'application/json'
        self.charset = 'utf8'
        self.response.out.write(json.dumps(response))


class InboxHandler(BaseHandler):

    def get(self):
        account = self._get_account()
        if account:
            messages = Message.query(ancestor=account.key).order(Message.date)
            response = {
                'account': {
                    'email': account.email,
                    'expireIn': account.expire_in
                },
                'messages': [
                    {
                        'key': message.key.urlsafe(),
                        'sender': message.sender,
                        'date': to_timestamp(message.date),
                        'subject': message.subject
                    } for message in messages
                ]
            }
            self.response.content_type = 'application/json'
            self.charset = 'utf8'
            self.response.out.write(json.dumps(response))
        else:
            self.response.status = '410 Gone'


class MessageHandler(BaseHandler):

    def get(self, key):
        try:
            message_key = ndb.Key(urlsafe=key)
            message = message_key.get()
        except Exception as e:
            logging.exception(e)
            self.response.status = '404 Not Found'
        else:
            account = self._get_account()
            message_account_key = message_key.parent()
            if not account or account.key != message_account_key:
                self.response.status = '403 Forbidden'
            else:
                response = {
                    'message': {
                        'key': key,
                        'sender': message.sender,
                        'date': to_timestamp(message.date),
                        'subject': message.subject,
                        'html': message.html
                    }
                }
                self.response.content_type = 'application/json'
                self.charset = 'utf8'
                self.response.out.write(json.dumps(response))


class NewAccountHandler(BaseHandler):

    def get(self):
        account = self._get_account()
        if account:
            account.valid_until = datetime.now()
            account.put()
            logging.info("Account closed: %s" % account.email)
        account = self._create_account()
        logging.info("Account created: %s" % account.email)
        response = {
            'account': {
                'email': account.email,
                'expireIn': account.expire_in
            }
        }
        self.response.content_type = 'application/json'
        self.charset = 'utf8'
        self.response.out.write(json.dumps(response))


class ResetTimerHandler(BaseHandler):

    def get(self):
        account = self._get_account()
        if account and account.is_valid:
            account.valid_until = datetime.now()+timedelta(seconds=600)
            account.put()
            response = {
                'account': {
                    'email': account.email,
                    'expireIn': account.expire_in
                }
            }
            self.response.content_type = 'application/json'
            self.charset = 'utf8'
            self.response.out.write(json.dumps(response))
        else:
            self.response.status = '403 Forbidden'


config = {}
config['webapp2_extras.sessions'] = {
    'secret_key': 'my-super-secret-key',
}

app = webapp2.WSGIApplication([
    webapp2.Route('/init', InitHandler),
    webapp2.Route('/inbox', InboxHandler),
    webapp2.Route('/message/<key>', MessageHandler),
    webapp2.Route('/newAccount', NewAccountHandler),
    webapp2.Route('/resetTimer', ResetTimerHandler),
], config=config, debug=True)
