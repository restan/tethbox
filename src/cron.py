from datetime import datetime

from google.appengine.ext import ndb
import webapp2

from tethbox.model import Account, Message


class ClearAccountsHandler(webapp2.RequestHandler):

    def get(self):
        messages_to_delete = []
        accounts_to_clear = Account.query(
            ndb.AND(Account.valid_until < datetime.now(),
                    Account.cleared == False)
        ).fetch()
        for account in accounts_to_clear:
            messages_to_delete.extend(Message.query(ancestor=account.key).fetch())
            account.cleared = True
        if messages_to_delete:
            ndb.delete_multi([message.key for message in messages_to_delete])
        if accounts_to_clear:
            ndb.put_multi(accounts_to_clear)


app = webapp2.WSGIApplication([
    webapp2.Route('/_cron/clearAccounts', ClearAccountsHandler)
], debug=True)