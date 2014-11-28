from datetime import datetime, timedelta
import json
import logging
import string

from google.appengine.api import app_identity
from google.appengine.ext import ndb
import os
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


def max_account_validity():
    return datetime.now() + \
        timedelta(seconds=config['tethbox']['account_max_seconds'])


def get_account(session):
    account_id = session.get('account_id')
    if account_id:
        account = Account.get_by_id(account_id)
        if account and account.is_valid:
            return account


def create_account(session):
    account = Account(
        email=create_unique_email_address(),
        valid_until=max_account_validity()
    )
    account.put()
    session['account_id'] = account.key.id()
    return account


def create_unique_email_address():
    _, number = Account.allocate_ids(1)
    user = base62_encode(number)
    return '%s@%s.appspotmail.com' % (user, app_identity.get_application_id())


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


class JsonHandler(BaseHandler):

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
            logging.info("Account created: %s" % account.email)
        return {
            'account': {
                'email': account.email,
                'expireIn': account.expire_in
            }
        }


class InboxHandler(JsonHandler):

    def get_json(self):
        account = get_account(self.session)
        if account:
            messages = Message.query(ancestor=account.key).order(Message.date)
            return {
                'account': {
                    'email': account.email,
                    'expireIn': account.expire_in
                },
                'messages': [
                    {
                        'key': message.key.urlsafe(),
                        'sender': message.sender,
                        'date': to_timestamp(message.date),
                        'subject': message.subject,
                        'read': message.read
                    } for message in messages
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
                    'message': {
                        'key': key,
                        'sender': message.sender,
                        'date': to_timestamp(message.date),
                        'subject': message.subject,
                        'html': message.html
                    }
                }


class NewAccountHandler(JsonHandler):

    def get_json(self):
        account = get_account(self.session)
        if account:
            account.valid_until = datetime.now()
            account.put()
            logging.info("Account closed: %s" % account.email)
        account = create_account(self.session)
        logging.info("Account created: %s" % account.email)
        return {
            'account': {
                'email': account.email,
                'expireIn': account.expire_in
            }
        }


class ResetTimerHandler(JsonHandler):

    def get_json(self):
        account = get_account(self.session)
        if account and account.is_valid:
            account.valid_until = max_account_validity()
            account.put()
            return {
                'account': {
                    'email': account.email,
                    'expireIn': account.expire_in
                }
            }
        else:
            self.abort(403)


config = {
    'webapp2_extras.sessions': {
        'secret_key': os.environ['SESSION_SECRET_KEY'],
    },
    'tethbox': {
        'account_max_seconds': int(os.environ['ACCOUNT_MAX_SECONDS']),
    },
}

app = webapp2.WSGIApplication([
    webapp2.Route('/init', InitHandler),
    webapp2.Route('/inbox', InboxHandler),
    webapp2.Route('/message/<key>', MessageHandler),
    webapp2.Route('/newAccount', NewAccountHandler),
    webapp2.Route('/resetTimer', ResetTimerHandler),
], config=config, debug=True)
