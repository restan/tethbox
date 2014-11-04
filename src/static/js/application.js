var tethbox = (function() {

	var api = (function() {
		return {
			init: function() {
				return $.getJSON('/init');
			},

			getInbox: function() {
				return $.getJSON('/inbox');
			},

			createNewAccount: function() {
				return $.getJSON('/newAccount');
			},

			resetAccountTimer: function() {
				return $.getJSON('/resetTimer');
			},

			getMessage: function(key) {
				return $.getJSON('/message/' + key);
			}
		};
	})();

	var account = null;
	var messages = [];
	var localTimer = null;

	var initButtons = function() {
		initCopyButton();
		initResetTimerButton();
		initNewAccountButton();
	}

	var initCopyButton = function() {
		var client = new ZeroClipboard($('.copy-button'));
		client.on('aftercopy', function(event) {
			event.target.blur();
		});
	}

	var initResetTimerButton = function() {
		$('#reset-timer-button').click(function() {
			resetAccountTimer();
			this.blur();
		});
	}

	var initNewAccountButton = function() {
		$('#new-account-button').click(function() {
			createNewAccount();
			this.blur();
		});
	}

	var initAccount = function() {
		api.init().done(function(data) {
			account = data.account;
			updateAccountValues();
			checkInbox();
	    });
	}

	var updateAccountValues = function() {
		updateEmailValue();
		updateTimerValue();
		if (account) {
			showInbox();
		} else {
			hideInbox();
		}
	}

	var updateEmailValue = function() {
		$('#email').val(account ? account.email : '');
	}

	var updateTimerValue = function() {
		$('#expire-in').val(account !== null ? timestampToReadable(account.expireIn) : '');
	}

	var showInbox = function() {
		$('#inbox').parent().removeClass('hidden');
	}

	var hideInbox = function() {
		$('#inbox').parent().addClass('hidden');
	}

	var checkInbox = function() {
		api.getInbox().done(function(data) {
			var accountChanged = account && account.email != data.account.email;
			if (accountChanged) {
				account = data.account;
				updateAccountValues();
			} else {
				account.expireIn = data.account.expireIn;
			}
			messages = data.messages;
			updateMessageList();
		}).fail(function(jqxhr, textStatus, error) {
			if (jqxhr.status == 410) {
				accountExpired();
			}
		});
	}

	var updateMessageList = function() {
		var newTbody = $('<tbody>');
		for (var i in messages) {
			var message = messages[i];
			$('<tr>').addClass(message.read ? '' : 'unread')
				.append($('<td>').text(message.sender))
				.append($('<td>').text(message.subject))
				.append($('<td>').text(new Date(message.date * 1000).toLocaleString()))
				.click({'key': message.key}, function(event) {
					openMessage(event.data.key);
					$(this).removeClass('unread');
				})
				.appendTo(newTbody);
		}
		$('#inbox tbody').replaceWith(newTbody);
	}

	var createNewAccount = function() {
		api.createNewAccount().done(function(data) {
			account = data.account;
			updateAccountValues();
			checkInbox();
			if (localTimer === null) {
				startLocalTimer();
			}
		});
	}

	var resetAccountTimer = function() {
		api.resetAccountTimer().done(function(data) {
			account = data.account;
			updateAccountValues();
		});
	}

	var openMessage = function(key) {
		api.getMessage(key).done(function(data) {
			displayMessage(data.message);
		});
	}

	var displayMessage = function(message) {
		$('#message-modal .modal-title').text(message.subject);
		$('#message-modal .modal-body').html(message.html);
		$('#message-modal').modal('show');
	}

	var accountExpired = function() {
		resetData();
	}

	var resetData = function() {
		account = null;
		messages = [];
		stopLocalTimer();
		updateAccountValues();
		updateMessageList();
	}

	var startLocalTimer = function() {
		localTimer = setTimeout(function(){
			startLocalTimer();
			if (account && account.expireIn > 0) {
				account.expireIn--;
				updateTimerValue();
			}
			var now = new Date();
			var checkInboxInterval = account && account.expireIn > 0 ? 10 : 1;
			if (now.getSeconds() % checkInboxInterval == 0) {
				checkInbox();
			}
		}, 1000);
	}

	var stopLocalTimer = function() {
		if (localTimer !== null) {
			clearTimeout(localTimer);
			localTimer = null;
		}
	}

	var timestampToReadable = function(timestamp) {
		var date = new Date(timestamp * 1000);
		var minutes = '' + date.getMinutes();
		var seconds = (date.getSeconds() < 10 ? '0' : '') + date.getSeconds();
		return minutes + ':' + seconds;
	}

	return {
		init: function() {
			initButtons();
			initAccount();
			startLocalTimer();
		}
	};
}());
