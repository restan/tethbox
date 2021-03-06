var tethbox = (function() {

	var api = {
		init: function() {
			return $.getJSON('/account/init');
		},

		getInbox: function() {
			return $.getJSON('/account/inbox');
		},

		createNewAccount: function() {
			return $.getJSON('/account/new');
		},

		extendTime: function() {
			return $.getJSON('/account/extend');
		},

		getMessage: function(key) {
			return $.getJSON('/message/' + key);
		},

		forwardMessage: function(key, address) {
			return $.post('/message/' + key + '/forward', {'address': address});
		}
	};

	var accountManager = function() {

		var localTimer = function() {
			var timer = null;

			function start() {
				timer = setTimeout(function(){
					start();
					account = accountManager.getAccount();
					if (account && account.expireIn > 0) {
						account.expireIn--;
						bindAccountValues();
					}
					var now = new Date();
					var checkInboxInterval = account && account.expireIn > 0 ? 10 : 1;
					if (now.getSeconds() % checkInboxInterval == 0) {
						checkInbox();
					}
				}, 1000);
			}

			function stop() {
				if (!isStopped()) {
					clearTimeout(timer);
					timer = null;
				}
			}

			function isStopped() {
				return timer === null;
			}

			return {
				start: start,
				stop: stop,
				isStopped: isStopped
			}
		}();

		var account = null;
		var messages = [];

		function init() {
			return api.init().done(function(data) {
				setAccount(data.account);
				checkInbox().done(function() {
					localTimer.start();
				});
			});
		}

		function checkInbox() {
			return api.getInbox().done(function(data) {
				setAccount(data.account);
				setMessages(data.messages);
			}).fail(function(jqxhr, textStatus, error) {
				if (jqxhr.status == 410) {
					expireAccount();
				}
			});
		}

		function getAccount() {
			return account
		}

		function setAccount(_account) {
			account = _account;
			bindAccountValues();
		}

		function bindAccountValues() {
			$('#email').val(account ? account.email : '');
			$('#expire-in').val(account !== null ? readableTimedelta(account.expireIn) : '');
			if (account) {
				showAccount();
			} else {
				hideAccount();
			}
		}

		function getMessage(key) {
			for (var i in messages) {
				if (messages[i].key == key) {
					return messages[i];
				}
			}
		}

		function setMessages(_messages) {
			for (var i in _messages) {
				var _message = _messages[i];
				$.extend(_message, getMessage(_message.key));
			}
			messages = _messages;
			bindMessagesValues();
		}

		function bindMessagesValues() {
			var newTbody = $('<tbody>');
			for (var i in messages) {
				var message = messages[i];
				var message_sender = message.sender_name || message.sender_address;
				$('<tr>').addClass(message.read ? 'active' : '')
					.append($('<td>').text(message_sender))
					.append($('<td>').text(message.subject || '(no subject)'))
					.append($('<td>').text(timestampToLocaleTimeString(message.date)))
					.click({'message': message}, function(event) {
						openMessage(event.data.message);
						setMessageAsRead(event.data.message);
					})
					.appendTo(newTbody);
			}
			$('#inbox tbody').replaceWith(newTbody);
			updatePageTitle();
		}

		function openMessage(message) {
			if (message.fetched) {
			    messageModal.show(message);
			} else {
				api.getMessage(message.key).done(function(data) {
					$.extend(message, data.message);
					message.fetched = true;
					messageModal.show(message);
				});
			}
		}

		function setMessageAsRead(message) {
			message.read = true;
			bindMessagesValues();
		}

		function updatePageTitle() {
			var unreadMessages = 0;
			for (var i in messages) {
				if (!messages[i].read) {
					unreadMessages++;
				}
			}
			var title = "TethBox " + (unreadMessages > 0 ? "["+unreadMessages+"] " : "") + "- temporary mailbox";
			$('head title').text(title);
		}

		function extendTime() {
			api.extendTime().done(function(data) {
				setAccount(data.account);
			});
		}

		function expireAccount() {
			localTimer.stop();
			setAccount(null);
			setMessages([]);
			messageModal.close();
			forwardModal.close();
		}

		function createNewAccount() {
			api.createNewAccount().done(function(data) {
				setAccount(data.account);
				checkInbox();
				if (localTimer.isStopped()) {
					localTimer.start();
				}
			});
		}

		function showAccount() {
			$('#account-details').removeClass('hidden');
			$('#inbox').parent().removeClass('hidden');
		}

		function hideAccount() {
			$('#inbox').parent().addClass('hidden');
			$('#account-details').addClass('hidden');
		}

		return {
			init: init,
			extendTime: extendTime,
			createNewAccount: createNewAccount,
			getAccount: getAccount,
			setAccount: setAccount
		};
	}();

	var messageModal = function() {
		var message = null;

		function initElements() {
			function initForwardModalButton() {
				$('#forward-modal-button').click(function() {
					var _message = message;
					close();
					forwardModal.show(_message);
				});
			}

			function initModal() {
				$('#message-modal').on('hidden.bs.modal', function (e) {
					setMessage(null);
				});
			}

			initForwardModalButton();
			initModal();
		}

		function show(_message) {
			setMessage(_message);
			$('#message-modal').modal('show');
		}

		function setMessage(_message) {
			message = _message;
			bindMessageValues();
		}

		function bindMessageValues() {
			var subject='', sender_name='', sender_address='', date='', html='';
			if (message) {
				subject = message.subject || '(no subject)';
				date = timestampToLocaleString(message.date);
				html = message.html || '(no body)';
				if (message.sender_name) {
					sender_name = message.sender_name;
					sender_address = '<' + message.sender_address + '>';
				} else {
					sender_name = message.sender_address;
				}
			}
			$('#message-modal .modal-header .subject').text(subject);
			$('#message-modal .modal-header .sender span').text(sender_name);
			$('#message-modal .modal-header .sender small').text(sender_address);
			$('#message-modal .modal-header .date span').text(date);
			$('#message-modal .modal-body').html(html);
			bindAttachments();
		}

		function bindAttachments() {
			var attachments = message ? message.attachments : [];
			var newAttachmentList = $('<ul class="attachments">');
			for (var i in attachments) {
				var attachment = attachments[i];
				$('<li>')
					.append($('<span class="glyphicon glyphicon-paperclip" aria-hidden="true">'))
					.append($('<a>').attr({'href': attachment.url}).text(attachment.filename))
					.append(' (' + readableFileSize(attachment.size) + ')')
					.appendTo(newAttachmentList);
			}
			$('#message-modal .attachments').replaceWith(newAttachmentList);
			if (attachments.length == 0) {
				$('#message-modal .modal-footer').addClass('hidden');
			} else {
				$('#message-modal .modal-footer').removeClass('hidden');
			}
		}

		function close() {
			$('#message-modal').modal('hide');
		}

		return {
			initElements: initElements,
			show: show,
			close: close,
		};
	}();

	var forwardModal = function() {
		var message = null;

		function initElements() {
			function initAddressInput() {
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

			function initForwardButton() {
				$('#forward-button').click(function() {
					this.blur();
					var button = $(this).addClass('disabled').button('forwarding');
					forwardMessage(message).always(function() {
						button.button('reset').removeClass('disabled');
					});
				});
			}

			function initModal() {
				$('#forward-modal').on('hidden.bs.modal', function (e) {
					message = null;
					$('#forward-modal .alert').remove();
					$('#forward-address').val('');
					$('#forward-address').parent().removeClass('has-success').removeClass('has-warning');
				});
			}

			initAddressInput();
			initForwardButton();
			initModal();
		}

		function checkFrowardEmailAddressValidity() {
			emailAddress = $('#forward-address').val();
			if (emailAddress.length > 0) {
				if (/^[^@]+@[^@]+\.[^@]+$/.test(emailAddress)) {
					$('#forward-address').parent().removeClass('has-warning').addClass('has-success');
				} else {
					$('#forward-address').parent().removeClass('has-success').addClass('has-warning');
				}
			} else {
				$('#forward-address').parent().removeClass('has-success').removeClass('has-warning');
			}
		}

		function forwardMessage(message) {
			hideAlert();
			var address = $('#forward-address').val();
			return api.forwardMessage(message.key, address).done(function(data) {
				showAlert('success', 'Email forwarded successfully to <strong>' + address + '</strong>.');
				$('#forward-address').val('');
				checkFrowardEmailAddressValidity();
			}).fail(function(data) {
				if (data.status == 400 && data.responseJSON && data.responseJSON.error) {
					showAlert('danger', data.responseJSON.error);
				} else {
					showAlert('danger', 'Cannot forward your message at this time.');
					console.log(data);
				}
			});
		}

		function showAlert(type, text) {
			var alertClass = 'alert-' + type;
			$('<div class="alert" role="alert">')
				.addClass(alertClass)
				.html(text)
				.appendTo('#forward-modal .modal-body');
		}

		function hideAlert() {
			$('#forward-modal .alert').remove();
		}

		function show(_message) {
			message = _message;
			$('#forward-modal').modal('show');
		}

		function close() {
			$('#forward-modal').modal('hide');
		}

		return {
			initElements: initElements,
			show: show,
			close: close,
		};
	}();

	function initElements() {
		function initEmailButton() {
			var clipboard = new Clipboard('.btn');
			clipboard.on('success', function(e) {
				e.clearSelection();
			});
		}

		function initExtendTimeButton() {
			$('#extend-time-button').click(function() {
				accountManager.extendTime();
				this.blur();
			});
		}

		function initNewAccountButton() {
			$('#new-account-button').click(function() {
				accountManager.createNewAccount();
				this.blur();
			});
		}

		initEmailButton();
		initExtendTimeButton();
		initNewAccountButton();
		messageModal.initElements();
		forwardModal.initElements();
	}

	function readableTimedelta(timedelta) {
		var date = new Date(timedelta * 1000);
		var minutes = '' + date.getMinutes();
		var seconds = (date.getSeconds() < 10 ? '0' : '') + date.getSeconds();
		return minutes + ':' + seconds;
	}

	function readableFileSize(bytes) {
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

	function timestampToLocaleString(timestamp) {
		return new Date(timestamp * 1000).toLocaleString()
	}

	function timestampToLocaleTimeString(timestamp) {
		return new Date(timestamp * 1000).toLocaleTimeString()
	}

	return {
		init: function() {
			initElements();
			accountManager.init();
		}
	};
}());
