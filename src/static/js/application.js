var tethbox = (function() {
	var account = null;
	var messages = [];
	var timer = null;

	var initButtons = function() {
		initCopyButton();
		initResetTimerButton();
		initNewAccountButton();
	}

	var initCopyButton = function() {
		new ZeroClipboard($(".copy-button"));
	}

	var initResetTimerButton = function() {
		$('#resetTimer').click(resetTimer);
	}

	var initNewAccountButton = function() {
		$('#newAccount').click(newAccount);
	}

	var getAccount = function() {
		$.getJSON(
			'/init',
			function(data) {
				account = data.account;
				updateAccountValues();
				checkInbox();
			}
		);
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
		$('#expireIn').val(account !== null ? timestampToReadable(account.expireIn) : '');
	}

	var showInbox = function() {
		$('#inbox').parent().removeClass('hidden');
	}

	var hideInbox = function() {
		$('#inbox').parent().addClass('hidden');
	}

	var checkInbox = function() {
		$.getJSON(
			'/inbox'
		).done(function(data) {
				var accountChanged = account.email != data.account.email;
				if (accountChanged) {
					account = data.account;
					updateAccountValues();
				} else {
					account.expireIn = data.account.expireIn;
				}
				messages = data.messages;
				updateMessageList();
			}
		).fail(function(jqxhr, textStatus, error) {
			if (jqxhr.status == 410) {
				accountExpired();
			}
		});
	}

	var updateMessageList = function() {
		var newTbody = $('<tbody>');
		for (var i in messages) {
			var message = messages[i];
			$("<tr>")
				.append($('<td>').text(message.sender))
				.append($('<td>').text(message.subject))
				.append($('<td>').text(new Date(message.date * 1000).toLocaleString()))
				.click(function() {
					openMessage(message.key);
				})
				.appendTo(newTbody);
		}
		$('#inbox tbody').replaceWith(newTbody);
	}

	var startTimer = function() {
		timer = setTimeout(function(){
			startTimer();
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

	var stopTimer = function() {
		if (timer !== null) {
			clearTimeout(timer);
			timer = null;
		}
	}

	var accountExpired = function() {
		resetData();
	}

	var resetData = function() {
		account = null;
		messages = [];
		stopTimer();
		updateAccountValues();
		updateMessageList();
	}

	var newAccount = function() {
		$.getJSON(
			'/newAccount',
			function(data) {
				account = data.account;
				updateAccountValues();
				checkInbox();
				startTimer();
			}
		);
	}

	var resetTimer = function() {
		$.getJSON(
			'/resetTimer',
			function(data) {
				account = data.account;
				updateAccountValues();
			}
		);
	}

	var openMessage = function(key) {
		getMessage(key, displayMessage);
	}

	var getMessage = function(key, callback) {
		$.getJSON(
			'/message/' + key,
			function(data) {
				callback(data.message);
			}
		);
	}

	var displayMessage = function(message) {
		$('#messageModal .modal-title').text(message.subject);
		$('#messageModal .modal-body').html(message.html);
		$('#messageModal').modal('show');
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
			getAccount();
			startTimer();
		}
	}
}());
