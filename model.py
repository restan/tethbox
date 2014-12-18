from datetime import datetime, timedelta
import logging
import string

import cloudstorage as gcs
from google.appengine.api import app_identity
from google.appengine.ext import ndb, blobstore


BASE62_DIGITS = string.digits + string.letters
BASE62_SIZE = len(BASE62_DIGITS)
EMAIL_ADDRESS_PATTERN = '%s@%s.appspotmail.com'
ACCOUNT_MAX_SECONDS = 600


def base62_encode(number):
    result = ''
    while number > 0:
        result = BASE62_DIGITS[number % BASE62_SIZE] + result
        number /= BASE62_SIZE
    return result


def create_unique_email_address():
    _, number = Account.allocate_ids(1)
    user = base62_encode(number)
    application_id = app_identity.get_application_id()
    return EMAIL_ADDRESS_PATTERN % (user, application_id)


def max_account_validity():
    return datetime.now() + \
        timedelta(seconds=ACCOUNT_MAX_SECONDS)


class Account(ndb.Model):
    email = ndb.StringProperty(required=True)
    created_at = ndb.DateTimeProperty(required=True, auto_now_add=True)
    valid_until = ndb.DateTimeProperty(required=True)
    cleared = ndb.BooleanProperty(required=True, default=False)

    @property
    def expire_in(self):
        return int((self.valid_until - datetime.now()).total_seconds())

    @property
    def is_valid(self):
        return self.valid_until > datetime.now()

    @classmethod
    def get_by_email(cls, email):
        return cls.query(Account.email == email).get()

    @classmethod
    def create(cls):
        account = cls(
            email=create_unique_email_address(),
            valid_until=max_account_validity()
        )
        account.put()
        logging.info("Account created: %s" % account.email)
        return account

    def close(self):
        self.valid_until = datetime.now()
        self.put()
        logging.info("Account closed: %s" % self.email)

    def extend_validity(self):
        self.valid_until = max_account_validity()
        self.put()
        logging.info("Account validity extended: %s" % self.email)

    def clear(self):
        logging.info("Clearing account: %s" % self.email)
        messages_to_delete = Message.query(ancestor=self.key).fetch()
        for message in messages_to_delete:
            message.delete()
        self.cleared = True
        self.put()


class Message(ndb.Model):
    sender_name = ndb.StringProperty(required=False)
    sender_address = ndb.StringProperty(required=True)
    to = ndb.StringProperty(required=True)
    reply_to = ndb.StringProperty(required=False)
    cc = ndb.StringProperty(required=False)
    bcc = ndb.StringProperty(required=False)
    subject = ndb.StringProperty(required=True)
    date = ndb.DateTimeProperty(required=True)
    body = ndb.TextProperty()
    html = ndb.TextProperty()
    read = ndb.BooleanProperty(required=True, default=False)

    def delete(self):
        attachments_to_delete = Attachment.query(ancestor=self.key).fetch()
        for attachment in attachments_to_delete:
            attachment.delete()
        self.key.delete()


class Attachment(ndb.Model):
    filename = ndb.StringProperty(required=True)
    size = ndb.IntegerProperty(required=True)
    gcs_filename = ndb.StringProperty(required=True)

    @property
    def blobkey(self):
        return blobstore.BlobKey(blobstore.create_gs_key('/gs%s' % self.gcs_filename))

    def delete(self):
        try:
            gcs.delete(self.gcs_filename)
        except gcs.NotFoundError, e:
            logging.warning('GCS file not found: %s' % self.gcs_filename)
        self.key.delete()