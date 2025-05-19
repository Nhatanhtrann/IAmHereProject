// Chat functionality với typing effect như ChatGPT
class ModernChatInterface {
    constructor() {
        this.chatMessages = document.getElementById('chatMessages');
        this.userInput = document.getElementById('userInput');
        this.sendMessageBtn = document.getElementById('sendMessage');
        this.resetChatBtn = document.getElementById('resetChat');
        
        // API URLs
        this.apiUrl = 'http://localhost:5001/chat';
        this.resetUrl = 'http://localhost:5001/reset';
        
        // Typing effect settings
        this.typingSpeed = 10; // milliseconds per character
        this.currentTypingTimeout = null;
        
        // Prevent duplicate messages
        this.lastUserMessage = '';
        this.lastBotMessage = '';
        
        this.init();
    }

    init() {
        // Event listeners
        this.sendMessageBtn.addEventListener('click', () => this.handleSendMessage());
        this.userInput.addEventListener('keypress', (e) => this.handleKeyPress(e));
        this.resetChatBtn.addEventListener('click', () => this.handleResetChat());
        
        // Auto focus on input
        this.userInput.focus();
        
        // Add online indicator to header
        this.addOnlineIndicator();
        
        // Add keyboard shortcuts
        this.addKeyboardShortcuts();
        
        // Add connection status monitoring
        this.addConnectionStatus();
    }

    addOnlineIndicator() {
        const header = document.querySelector('.chat-header h2');
        if (header && !header.querySelector('.online-indicator')) {
            const indicator = document.createElement('span');
            indicator.className = 'online-indicator';
            indicator.title = 'Chatbot đang online';
            header.appendChild(indicator);
        }
    }

    addKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Ctrl/Cmd + R for reset (prevent browser refresh)
            if ((e.ctrlKey || e.metaKey) && e.key === 'r') {
                e.preventDefault();
                this.handleResetChat();
            }
            
            // Escape to focus input
            if (e.key === 'Escape') {
                this.userInput.focus();
            }
        });
    }

    addConnectionStatus() {
        // Monitor connection status
        window.addEventListener('online', () => {
            this.showConnectionStatus('Đã kết nối lại', 'success');
        });
        
        window.addEventListener('offline', () => {
            this.showConnectionStatus('Mất kết nối internet', 'error');
        });
    }

    showConnectionStatus(message, type) {
        const statusDiv = document.createElement('div');
        statusDiv.className = `connection-status ${type}`;
        statusDiv.textContent = message;
        
        document.body.appendChild(statusDiv);
        
        // Remove after 3 seconds
        setTimeout(() => {
            if (statusDiv.parentElement) {
                statusDiv.remove();
            }
        }, 3000);
    }

    handleKeyPress(event) {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            this.handleSendMessage();
        }
    }

    async handleSendMessage() {
        const message = this.userInput.value.trim();
        if (!message || this.isProcessing()) return;

        // Prevent duplicate messages
        if (message === this.lastUserMessage) return;
        this.lastUserMessage = message;

        try {
            // Add user message
            this.addMessage(message, 'user');
            this.userInput.value = '';
            this.setProcessingState(true);
            
            // Show typing indicator
            this.showTypingIndicator();

            // Send to API
            const response = await fetch(this.apiUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message })
            });

            // Handle response
            await this.handleApiResponse(response);

        } catch (error) {
            console.error('Error sending message:', error);
            this.hideTypingIndicator();
            this.addMessage('Xin lỗi, đã có lỗi kết nối tới server. Vui lòng thử lại sau.', 'bot');
        } finally {
            this.setProcessingState(false);
            // Reset duplicate prevention after processing
            setTimeout(() => {
                this.lastUserMessage = '';
            }, 1000);
        }
    }

    async handleApiResponse(response) {
        this.hideTypingIndicator();
        
        if (!response.ok) {
            let errorMessage = `Lỗi ${response.status}: ${response.statusText}`;
            try {
                const errorData = await response.json();
                if (errorData.error) {
                    errorMessage = errorData.error;
                    if (errorData.detail) {
                        errorMessage += ": " + errorData.detail;
                    }
                }
            } catch (e) {
                console.error('Cannot parse error JSON:', e);
            }
            this.addMessage(errorMessage, 'bot');
            return;
        }

        const data = await response.json();
        if (data.reply || data.response) {
            const botMessage = data.reply || data.response;
            
            // Prevent duplicate bot messages
            if (botMessage !== this.lastBotMessage) {
                this.lastBotMessage = botMessage;
                await this.addMessageWithTypingEffect(botMessage, 'bot');
            }
        } else if (data.error) {
            this.addMessage(`Lỗi từ AI: ${data.error}`, 'bot');
        } else {
            this.addMessage('Đã nhận được phản hồi nhưng không có nội dung.', 'bot');
        }
    }

    async handleResetChat() {
        if (!confirm("Bạn có chắc chắn muốn bắt đầu lại cuộc trò chuyện không?")) {
            return;
        }

        try {
            this.setProcessingState(true);
            this.showTypingIndicator();

            const response = await fetch(this.resetUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'reset' })
            });

            this.hideTypingIndicator();

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                this.addMessage(errorData.error || 'Không thể reset cuộc trò chuyện.', 'bot');
                return;
            }

            const data = await response.json();
            
            // Clear chat and add welcome message
            this.chatMessages.innerHTML = '';
            const welcomeMessage = data.message || "Cuộc trò chuyện đã được làm mới. Tôi sẵn sàng lắng nghe bạn!";
            await this.addMessageWithTypingEffect(welcomeMessage, 'bot');
            
            // Reset duplicate prevention
            this.lastUserMessage = '';
            this.lastBotMessage = '';

        } catch (error) {
            console.error('Error resetting chat:', error);
            this.hideTypingIndicator();
            this.addMessage('Lỗi khi reset cuộc trò chuyện. Vui lòng thử lại.', 'bot');
        } finally {
            this.setProcessingState(false);
        }
    }

    // Improved message formatting function
    formatMessageText(text) {
        // Clean up the text first
        text = text.trim();
        
        // Replace **text** with simple bold
        text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        
        // Replace *text* with italic
        text = text.replace(/\*([^*]+)\*/g, '<em>$1</em>');
        
        // Replace "quoted text" with styled quotes (no vertical bar)
        text = text.replace(/"([^"]+)"/g, '<span class="quote">"$1"</span>');
        
        // Convert line breaks to HTML
        text = text.replace(/\n/g, '<br>');
        
        return text;
    }


    addMessage(text, sender) {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message', sender);
        
        const textDiv = document.createElement('div');
        textDiv.classList.add('text');
        
        // Format the text with better styling
        const formattedText = this.formatMessageText(text);
        textDiv.innerHTML = formattedText;
        
        messageDiv.appendChild(textDiv);
        
        // Add timestamp
        const timestamp = document.createElement('span');
        timestamp.className = 'message-timestamp';
        timestamp.textContent = new Date().toLocaleTimeString('vi-VN', {
            hour: '2-digit',
            minute: '2-digit'
        });
        messageDiv.appendChild(timestamp);
        
        this.chatMessages.appendChild(messageDiv);
        this.scrollToBottom();
        
        return textDiv;
    }

    async addMessageWithTypingEffect(text, sender) {
        // Create message container
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message', sender);
        
        const textDiv = document.createElement('div');
        textDiv.classList.add('text');
        
        messageDiv.appendChild(textDiv);
        this.chatMessages.appendChild(messageDiv);
        this.scrollToBottom();

        // Format the text before typing
        const formattedText = this.formatMessageText(text);
        
        // Start typing effect with formatted text
        await this.typeFormattedMessage(textDiv, formattedText);
        
        // Add timestamp after typing is complete
        const timestamp = document.createElement('span');
        timestamp.className = 'message-timestamp';
        timestamp.textContent = new Date().toLocaleTimeString('vi-VN', {
            hour: '2-digit',
            minute: '2-digit'
        });
        messageDiv.appendChild(timestamp);
    }

    async typeFormattedMessage(element, formattedHtml) {
        // Clear any existing typing timeout
        if (this.currentTypingTimeout) {
            clearTimeout(this.currentTypingTimeout);
        }

        // For typing effect, we'll parse the HTML and type character by character
        // while preserving the HTML structure
        let displayText = '';
        let htmlBuffer = '';
        let insideTag = false;
        let charIndex = 0;
        
        return new Promise((resolve) => {
            const typeNextChar = () => {
                if (charIndex < formattedHtml.length) {
                    const char = formattedHtml[charIndex];
                    
                    if (char === '<') {
                        insideTag = true;
                        htmlBuffer = '<';
                    } else if (char === '>' && insideTag) {
                        insideTag = false;
                        htmlBuffer += '>';
                        displayText += htmlBuffer;
                        element.innerHTML = displayText;
                        htmlBuffer = '';
                        charIndex++;
                        setTimeout(typeNextChar, 10); // Fast for HTML tags
                        return;
                    } else if (insideTag) {
                        htmlBuffer += char;
                    } else {
                        // Regular character
                        displayText += char;
                        element.innerHTML = displayText;
                        
                        // Variable speed based on character
                        let delay = this.typingSpeed;
                        if (char === '.') delay = this.typingSpeed * 3;
                        else if (char === ',') delay = this.typingSpeed * 2;
                        else if (char === ' ') delay = this.typingSpeed * 0.5;
                        else delay = this.typingSpeed + Math.random() * 10;
                        
                        this.scrollToBottom();
                        charIndex++;
                        this.currentTypingTimeout = setTimeout(typeNextChar, delay);
                        return;
                    }
                    
                    charIndex++;
                    setTimeout(typeNextChar, 1);
                } else {
                    resolve();
                }
            };

            typeNextChar();
        });
    }

    showTypingIndicator() {
        // Remove existing typing indicator
        this.hideTypingIndicator();
        
        const typingDiv = document.createElement('div');
        typingDiv.classList.add('message', 'bot', 'typing-indicator');
        typingDiv.id = 'typing-indicator';
        
        const textDiv = document.createElement('div');
        textDiv.classList.add('text');
        textDiv.innerHTML = 'Đang nhập<span>.</span><span>.</span><span>.</span>';
        
        typingDiv.appendChild(textDiv);
        this.chatMessages.appendChild(typingDiv);
        this.scrollToBottom();
    }

    hideTypingIndicator() {
        const typingIndicator = document.getElementById('typing-indicator');
        if (typingIndicator) {
            typingIndicator.remove();
        }
    }

    setProcessingState(isProcessing) {
        this.userInput.disabled = isProcessing;
        this.sendMessageBtn.disabled = isProcessing;
        this.resetChatBtn.disabled = isProcessing;
        
        if (!isProcessing) {
            this.userInput.focus();
        }
        
        // Update button text
        if (isProcessing) {
            this.sendMessageBtn.textContent = 'Đang gửi...';
        } else {
            this.sendMessageBtn.textContent = 'Gửi';
        }
    }

    isProcessing() {
        return this.sendMessageBtn.disabled;
    }

    scrollToBottom() {
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    const chatInterface = new ModernChatInterface();
});