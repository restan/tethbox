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
from model import Account, Message, Attachment


lxml.html.defs.safe_attrs |= {'style'}

ADDRESS_HEADER_REGEX = re.compile(r'(.*)<(.+)>')


def parse_address_header(address_header):
    address_match = ADDRESS_HEADER_REGEX.match(address_header)
    if address_match:
        name, address = map(lambda s: s.strip(' "'), address_match.groups())
        return name or None, address
    else:
        return None, address_header.strip()


def create_gcs_attachment_filename(message):
    return '/%s/attachments/%d/%s' % (
        app_identity.get_default_gcs_bucket_name(),
        message.key.id(),
        str(uuid.uuid4()).replace('-', '')
    )


def store_gcs_file(data, gsc_filename, orig_filename):
    content_type = mimetypes.guess_type(orig_filename)[0]
    if type(data) is unicode:
        data = data.encode('utf8')
        if content_type is not None:
            content_type += '; charset=UTF-8'
    with gcs.open(gsc_filename, 'w', content_type) as gsc_file:
        gsc_file.write(data)


def get_attachment_size(data):
    if type(data) is unicode:
        return len(data.encode('utf8'))
    return len(data)


class IncomingMailHandler(InboundMailHandler):

    def receive(self, mail_message):
        logging.info("Received a message to: " + mail_message.to)
        self._store_message(mail_message)

    def _store_message(self, mail_message):
        receiver_name, receiver_address = parse_address_header(mail_message.to)
        account = Account.get_by_email(receiver_address)
        if not account or account.valid_until < datetime.now():
            return
        sender_name, sender_address = parse_address_header(mail_message.sender)
        db_message = Message(
            parent=account.key,
            sender_name=sender_name,
            sender_address=sender_address,
            receiver_name=receiver_name,
            receiver_address=receiver_address,
            reply_to=getattr(mail_message, 'reply_to', None),
            cc=getattr(mail_message, 'cc', None),
            bcc=getattr(mail_message, 'bcc', None),
            subject=mail_message.subject,
            date=datetime.now(),
            body=mail_message.body.decode(),
            html=clean_html(mail_message.html.decode())
        )
        db_message.put()
        self._store_attachments(mail_message, db_message)

    def _store_attachments(self, mail_message, db_message):
        if hasattr(mail_message, 'attachments'):
            for mail_attachment in mail_message.attachments:
                self._store_attachment(mail_attachment, db_message)

    def _store_attachment(self, mail_attachment, db_message):
        gcs_filename = create_gcs_attachment_filename(db_message)
        data = mail_attachment.payload.decode()
        attachment_size = get_attachment_size(data)
        logging.info("Storing attachment: name=\"%s\" size=%d" % (mail_attachment.filename, attachment_size))
        store_gcs_file(data, gcs_filename, mail_attachment.filename)
        db_attachment = Attachment(
            parent=db_message.key,
            filename=mail_attachment.filename,
            size=attachment_size,
            gcs_filename=gcs_filename
        )
        db_attachment.put()



app = webapp2.WSGIApplication([IncomingMailHandler.mapping()], debug=True)
