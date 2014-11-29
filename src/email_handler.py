from datetime import datetime
import logging
import re

import lxml
from lxml.html.clean import clean_html
from google.appengine.ext.webapp.mail_handlers import InboundMailHandler
import webapp2

from tethbox.model import Account, Message


lxml.html.defs.safe_attrs |= {'style'}

EXTENDED_SENDER_REGEX = re.compile(r'(.+)<(.+)>')


def parse_sender(sender):
    sender_match = EXTENDED_SENDER_REGEX.match(sender)
    if sender_match:
        return sender_match.group(1), sender_match.group(2)
    else:
        return None, sender


class IncomingMailHandler(InboundMailHandler):

    def receive(self, mail_message):
        logging.info("Received a message to: " + mail_message.to)
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
        # TODO: store attachments


app = webapp2.WSGIApplication([IncomingMailHandler.mapping()], debug=True)
