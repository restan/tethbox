import cgi
from datetime import datetime, timedelta
import logging
import string

import lxml.html
import cloudstorage as gcs
from google.appengine.api import app_identity
from google.appengine.ext import ndb, blobstore


BASE62_DIGITS = string.digits + string.letters
BASE62_SIZE = len(BASE62_DIGITS)
EPOCH = datetime(1970, 1, 1)
EMAIL_ADDRESS_PATTERN = '%s@%s.appspotmail.com'
ACCOUNT_MAX_SECONDS = 600


def to_timestamp(datetime_):
    return int((datetime_ - EPOCH).total_seconds())


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

    @property
    def messages(self):
        return Message.query(ancestor=self.key).order(-Message.date)

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

    def api_repr(self):
        return {
            'email': self.email,
            'expireIn': self.expire_in
        }


class Message(ndb.Model):
    sender_name = ndb.StringProperty(required=False)
    sender_address = ndb.StringProperty(required=True)
    receiver_name = ndb.StringProperty(required=False)
    receiver_address = ndb.StringProperty(required=True)
    reply_to = ndb.StringProperty(required=False)
    cc = ndb.StringProperty(required=False)
    bcc = ndb.StringProperty(required=False)
    subject = ndb.StringProperty(required=False)
    date = ndb.DateTimeProperty(required=True)
    body = ndb.TextProperty()
    html = ndb.TextProperty()
    read = ndb.BooleanProperty(required=True, default=False)

    @property
    def attachments(self):
        return Attachment.query(Attachment.content_id == None, ancestor=self.key)

    @property
    def embedded_contents(self):
        return Attachment.query(Attachment.content_id != None, ancestor=self.key)

    @property
    def html_to_display(self):
        if self.html is not None:
            tree = lxml.html.fromstring(self.html)

            # Fix embedded content links
            for content in self.embedded_contents:
                content_id = content.content_id
                if content_id.startswith('<') and content_id.endswith('>'):
                    content_id = content_id[1:-1]
                for node in tree.xpath("//*[@src='cid:%s']" % content_id):
                    node.attrib['src'] = content.url

            # Amend links to open in new tab
            for link in tree.xpath("//a"):
                link.attrib['target'] = "_blank"

            return lxml.html.tostring(tree)
        elif self.body is not None:
            return cgi.escape(self.body).replace("\n", "<br>")
        else:
            return None

    def delete(self):
        attachments_to_delete = Attachment.query(ancestor=self.key).fetch()
        for attachment in attachments_to_delete:
            attachment.delete()
        self.key.delete()

    def api_repr(self, full=False):
        result = {
            'key': self.key.urlsafe(),
            'sender_name': self.sender_name,
            'sender_address': self.sender_address,
            'date': to_timestamp(self.date),
            'subject': self.subject,
            'read': self.read
        }
        if full:
            result['html'] = self.html_to_display
            result['attachments'] = [attachment.api_repr() for attachment in self.attachments]
        return result


class Attachment(ndb.Model):
    filename = ndb.StringProperty(required=True)
    content_id = ndb.StringProperty(required=False)
    size = ndb.IntegerProperty(required=True)
    gcs_filename = ndb.StringProperty(required=True)

    @property
    def blobkey(self):
        return blobstore.BlobKey(blobstore.create_gs_key('/gs%s' % self.gcs_filename))

    @property
    def url(self):
        return '/attachment/%s' % self.key.urlsafe()

    def delete(self):
        try:
            gcs.delete(self.gcs_filename)
        except gcs.NotFoundError:
            logging.warning('GCS file not found: %s' % self.gcs_filename)
        self.key.delete()

    def api_repr(self):
        return {
            'key': self.key.urlsafe(),
            'filename': self.filename,
            'size': self.size,
            'url': self.url
        }