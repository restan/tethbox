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

			extendTime: function() {
				return $.getJSON('/extendTime');
			},

			getMessage: function(key) {
				return $.getJSON('/message/' + key);
			},

			getAttachmentUrl: function(key) {
				return '/attachment/' + key;
			},

			forwardMessage: function(key, address) {
				return $.post('/message/' + key + '/forward', {'address': address});
			}
		};
	})();

	var account = null;
	var localTimer = null;

	var initElements = function() {
		initCopyButton();
		initExtendTimeButton();
		initNewAccountButton();
	}

	var initCopyButton = function() {
		var client = new ZeroClipboard($('.copy-button'));
		client.on('aftercopy', function(event) {
			event.target.blur();
		});
	}

	var initExtendTimeButton = function() {
		$('#extend-time-button').click(function() {
			extendTime();
			this.blur();
		});
	}

	var initNewAccountButton = function() {
		$('#new-account-button').click(function() {
			createNewAccount();
			this.blur();
		});
	}

	var initForwardModalButton = function(message) {
		$('#forward-modal-button').off('click').click(function() {
			hideMessage();
			openForwardModal(message);
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
			showAccount();
		} else {
			hideAccount();
		}
	}

	var updateEmailValue = function() {
		$('#email').val(account ? account.email : '');
	}

	var updateTimerValue = function() {
		$('#expire-in').val(account !== null ? readableTimedelta(account.expireIn) : '');
	}

	var showAccount = function() {
		$('#account-details').removeClass('hidden');
		$('#inbox').parent().removeClass('hidden');
	}

	var hideAccount = function() {
		$('#inbox').parent().addClass('hidden');
		$('#account-details').addClass('hidden');
	}

	var checkInbox = function() {
		api.getInbox().done(function(data) {
			var accountChanged = account && account.email != data.account.email;
			if (accountChanged) {
				account = data.account;
				updateAccountValues();
			} else if (account) {
				account.expireIn = data.account.expireIn;
			}
			setInboxMessages(data.messages);
		}).fail(function(jqxhr, textStatus, error) {
			if (jqxhr.status == 410) {
				accountExpired();
			}
		});
	}

	var setInboxMessages = function(messages) {
		var newTbody = $('<tbody>');
		for (var i in messages) {
			var message = messages[i];
			var message_sender = message.sender_name || message.sender_address;
			$('<tr>').addClass(message.read ? 'active' : '')
				.append($('<td>').text(message_sender))
				.append($('<td>').text(message.subject))
				.append($('<td>').text(timestampToLocaleString(message.date)))
				.click({'key': message.key}, function(event) {
					openMessage(event.data.key);
					$(this).addClass('active');
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

	var extendTime = function() {
		api.extendTime().done(function(data) {
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
		initForwardModalButton(message);
		$('#message-modal .modal-header .subject').text(message.subject);
		if (message.sender_name) {
			$('#message-modal .modal-header .sender span').text(message.sender_name);
			$('#message-modal .modal-header .sender small').text('<'+message.sender_address+'>');
		} else {
			$('#message-modal .modal-header .sender span').text(message.sender_address);
			$('#message-modal .modal-header .sender small').text('');
		}
		$('#message-modal .modal-header .date span').text(timestampToLocaleString(message.date));
		$('#message-modal .modal-body').html(message.html);
		updateAttachmentList(message.attachments);
		$('#message-modal').modal('show');
	}

	var hideMessage = function() {
		$('#message-modal').modal('hide');
	}

	var updateAttachmentList = function(attachments) {
		if (attachments.length == 0) {
			$('#message-modal .modal-footer').addClass('hidden');
		} else {
			var newAttachmentList = $('<ul class="attachments">');
			for (var i in attachments) {
				var attachment = attachments[i];
				$('<li>')
					.append($('<span class="glyphicon glyphicon-paperclip" aria-hidden="true">'))
					.append($('<a>').attr({'href': api.getAttachmentUrl(attachment.key)}).text(attachment.filename))
					.append(' (' + readableFileSize(attachment.size) + ')')
					.appendTo(newAttachmentList);
			}
			$('#message-modal .attachments').replaceWith(newAttachmentList);
			$('#message-modal .modal-footer').removeClass('hidden');
		}
	}

	var openForwardModal = function(message) {
		$('#forward-modal .alert').remove();
		$('#forward-address').val('');
		initForwardEmailInput(message);
		initForwardButton(message);
		$('#forward-modal').modal('show');
	}

	var initForwardEmailInput = function(message) {
		$('#forward-address').keyup(function(e) {
			if (e.which != 13) {
				checkFrowardEmailAddressValidity();
			}
		}).keypress(function(e) {
			if (e.which == 13) {
				e.preventDefault();
				forwardMessage(message);
			}
		});
	}

	var initForwardButton = function(message) {
		$('#forward-button').off('click').click(function() {
			forwardMessage(message);
		});
	}

	var checkFrowardEmailAddressValidity = function() {
		emailAddress = $('#forward-address').val();
		if (emailAddress.length > 0) {
			if (/^[^@]+@[^@]+\.[^@]+$/.test(emailAddress)) {
				$('#forward-address').parent().removeClass('has-warning').addClass('has-success');
			} else {
				$('#forward-address').parent().removeClass('has-success').addClass('has-warning');
			}
		}
	}

	var forwardMessage = function(message) {
		var showAlert = function(type, text) {
			var alertClass = 'alert-' + type;
			$('<div class="alert" role="alert">')
				.addClass(alertClass)
				.text(text)
				.appendTo('#forward-modal .modal-body');
		}

		$('#forward-modal .alert').remove();
		var address = $('#forward-address').val();
		api.forwardMessage(message.key, address).done(function(data) {
			showAlert('success', 'Email forwarded successfully.');
		}).fail(function(data) {
			if (data.status == 400 && data.responseJSON && data.responseJSON.error) {
				showAlert('danger', data.responseJSON.error);
			}
		});
	}

	var hideForwardModal = function() {
		$('#forward-modal').modal('hide');
	}

	var accountExpired = function() {
		resetData();
		hideMessage();
		hideForwardModal();
	}

	var resetData = function() {
		account = null;
		stopLocalTimer();
		updateAccountValues();
		setInboxMessages([]);
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

	var readableTimedelta = function(timedelta) {
		var date = new Date(timedelta * 1000);
		var minutes = '' + date.getMinutes();
		var seconds = (date.getSeconds() < 10 ? '0' : '') + date.getSeconds();
		return minutes + ':' + seconds;
	}

	var timestampToLocaleString = function(timestamp) {
		return new Date(timestamp * 1000).toLocaleString()
	}

	var readableFileSize = function(bytes) {
		var number = bytes;
		var units = ['kB', 'MB', 'GB'];
		var unit = 'B'
		for (var i in units) {
			if (number < 1000) {
				break;
			} else {
				number /= 1000;
				unit = units[i];
			}
		}
		return number.toFixed(1).replace('.0', '') + ' ' + unit;
	}

	return {
		init: function() {
			initElements();
			initAccount();
			startLocalTimer();
		}
	};
}());
