from datetime import datetime
import logging

import lxml
from lxml.html.clean import clean_html
from google.appengine.ext.webapp.mail_handlers import InboundMailHandler
import webapp2

from tethbox.model import Account, Message


lxml.html.defs.safe_attrs |= {'style'}


class IncomingMailHandler(InboundMailHandler):

    def receive(self, mail_message):
        logging.info("Received a message to: " + mail_message.to)
        account = Account.get_by_email(mail_message.to)
        if not account or account.valid_until < datetime.now():
            return
        message = Message(
            parent=account.key,
            sender=mail_message.sender,
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
