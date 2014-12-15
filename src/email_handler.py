from datetime import datetime
import logging
import mimetypes
import uuid

import re
import cloudstorage as gcs
import lxml
from lxml.html.clean import clean_html
from google.appengine.api import app_identity
from google.appengine.ext.webapp.mail_handlers import InboundMailHandler
import webapp2
from tethbox.model import Account, Message, Attachment


lxml.html.defs.safe_attrs |= {'style'}

EXTENDED_SENDER_REGEX = re.compile(r'(.+)<(.+)>')


def parse_sender(sender):
    sender_match = EXTENDED_SENDER_REGEX.match(sender)
    if sender_match:
        return sender_match.group(1), sender_match.group(2)
    else:
        return None, sender


def create_gcs_attachment_filename(message):
    return '/%s/attachments/%d/%s' % (
        app_identity.get_default_gcs_bucket_name(),
        message.key.id(),
        str(uuid.uuid4()).replace('-', '')
    )


def store_message(mail_message):
    account = Account.get_by_email(mail_message.to)
    if not account or account.valid_until < datetime.now():
        return
    sender_name, sender_address = parse_sender(mail_message.sender)
    message = Message(
        parent=account.key,
        sender_name=sender_name,
        sender_address=sender_address,
        to=mail_message.to,
        reply_to=getattr(mail_message, 'reply_to', None),
        cc=getattr(mail_message, 'cc', None),
        bcc=getattr(mail_message, 'bcc', None),
        subject=mail_message.subject,
        date=datetime.now(),
        body=mail_message.body.decode(),
        html=clean_html(mail_message.html.decode())
    )
    message.put()
    store_attachments(mail_message, message)


def store_attachments(mail_message, message):
    if hasattr(mail_message, 'attachments'):
        for mail_attachment in mail_message.attachments:
            store_attachment(mail_attachment, message)


def store_attachment(mail_attachment, message):
    gcs_filename = create_gcs_attachment_filename(message)
    data = mail_attachment.payload.decode()
    attachment_size = get_file_size(data)
    logging.info("Storing attachment: name=\"%s\" size=%d" % (mail_attachment.filename, attachment_size))
    store_gcs_file(data, gcs_filename, mail_attachment.filename)
    attachment = Attachment(
        parent=message.key,
        filename=mail_attachment.filename,
        size=attachment_size,
        gcs_filename=gcs_filename
    )
    attachment.put()


def store_gcs_file(data, gsc_filename, orig_filename):
    content_type = mimetypes.guess_type(orig_filename)[0]
    if type(data) is unicode:
        data = data.encode('utf8')
        if content_type is not None:
            content_type += '; charset=UTF-8'
    with gcs.open(gsc_filename, 'w', content_type) as gsc_file:
        gsc_file.write(data)


def get_file_size(f):
    if type(f) is unicode:
        return len(f.encode('utf8'))
    return len(f)


class IncomingMailHandler(InboundMailHandler):

    def receive(self, mail_message):
        logging.info("Received a message to: " + mail_message.to)
        store_message(mail_message)


app = webapp2.WSGIApplication([IncomingMailHandler.mapping()], debug=True)
