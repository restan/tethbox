from datetime import datetime

from google.appengine.ext import ndb
import webapp2
from model import Account


class ClearAccountsHandler(webapp2.RequestHandler):

    def get(self):
        accounts_to_clear = Account.query(
            ndb.AND(Account.valid_until < datetime.now(),
                    Account.cleared == False)
        ).fetch()
        for account in accounts_to_clear:
            account.clear()


app = webapp2.WSGIApplication([
    webapp2.Route('/_cron/clearAccounts', ClearAccountsHandler)
], debug=True)