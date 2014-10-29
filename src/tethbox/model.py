from datetime import datetime

from google.appengine.ext import ndb


class Account(ndb.Model):
    email = ndb.StringProperty(required=True)
    created_at = ndb.DateTimeProperty(required=True, auto_now_add=True)
    valid_until = ndb.DateTimeProperty(required=True)

    @property
    def expire_in(self):
        return int((self.valid_until - datetime.now()).total_seconds())

    @property
    def is_valid(self):
        return self.valid_until > datetime.now()

    @classmethod
    def get_by_email(cls, email):
        return cls.query(Account.email==email).get()


class Message(ndb.Model):
    sender = ndb.StringProperty(required=True)
    to = ndb.StringProperty(required=True)
    reply_to = ndb.StringProperty(required=False)
    cc = ndb.StringProperty(required=False)
    bcc = ndb.StringProperty(required=False)
    subject = ndb.StringProperty(required=True)
    date = ndb.DateTimeProperty(required=True)
    body = ndb.TextProperty()
    html = ndb.TextProperty()
    read = ndb.BooleanProperty(required=True, default=False)
