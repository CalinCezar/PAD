// gRPC Dashboard JavaScript - Adapted for HTTP/gRPC Bridge
class MessageBrokerDashboardGRPC {
    constructor() {
        this.brokerHost = 'localhost';
        this.brokerGrpcPort = 50051;
        this.brokerHttpBridgePort = 8080; // HTTP bridge for gRPC services
        this.isMonitoring = false;
        this.messageCount = 0;
        this.stats = {
            totalMessages: 0,
            activeSubscribers: 0,
            topicsCount: 0,
            messagesPerMinute: 0
        };
        this.messageHistory = [];
        this.startTime = Date.now();
        
        // Add offline message queue
        this.offlineQueue = [];
        this.isOffline = false;
        
        this.initializeEventListeners();
        this.startHealthCheck();
        this.updateLastSeen();
        
        // Auto-start monitoring when dashboard loads
        this.startMonitoring();
    }

    // Initialize all event listeners
    initializeEventListeners() {
        // Publish form
        document.getElementById('publish-form').addEventListener('submit', (e) => {
            e.preventDefault();
            this.publishMessage();
        });

        // Monitoring controls
        document.getElementById('toggle-monitoring').addEventListener('click', () => {
            this.toggleMonitoring();
        });

        document.getElementById('clear-messages').addEventListener('click', () => {
            this.clearMessages();
        });

        // Filter messages
        document.getElementById('filter-topic').addEventListener('input', (e) => {
            this.filterMessages(e.target.value);
        });

        // Auto-refresh stats every 5 seconds
        setInterval(() => {
            this.updateStats();
            this.updateLastSeen();
            this.getBrokerStatus(); // Check broker health
        }, 5000);
    }

    // Publish message through gRPC HTTP bridge
    async publishMessage() {
        const topic = document.getElementById('topic').value.trim();
        const content = document.getElementById('content').value.trim();
        const format = document.getElementById('format').value;

        if (!topic || !content) {
            this.showToast('Please fill in all fields', 'error');
            return;
        }

        try {
            // Convert format to gRPC enum value
            const formatMap = {
                'RAW': 0,
                'JSON': 1, 
                'XML': 2
            };

            const message = {
                topic: topic,
                content: content,
                format: formatMap[format] || 0,
                eventName: 'DashboardMessage'
            };

            const response = await this.publishToGRPCBridge(message);
            
            if (response && response.success) {
                this.showToast(`Message published successfully! Forwarded to ${response.subscriberCount} subscribers`);
                document.getElementById('publish-form').reset();
                this.updateStats();
                // Refresh messages if monitoring
                if (this.isMonitoring) {
                    this.refreshMessages();
                }
            } else {
                this.showToast('Failed to publish message: ' + (response?.message || 'Unknown error'), 'error');
            }
        } catch (error) {
            console.error('Publish error:', error);
            this.showToast('Connection error. Check if gRPC broker is running.', 'error');
        }
    }

    // Publish to gRPC via HTTP bridge
    async publishToGRPCBridge(message) {
        try {
            const response = await fetch(`http://${this.brokerHost}:${this.brokerHttpBridgePort}/grpc/publish`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                body: JSON.stringify(message)
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            return await response.json();
        } catch (error) {
            console.error('gRPC Bridge publish error:', error);
            throw error;
        }
    }

    // Toggle real-time monitoring
    toggleMonitoring() {
        const button = document.getElementById('toggle-monitoring');
        
        if (this.isMonitoring) {
            this.stopMonitoring();
            button.textContent = 'Start Monitoring';
            button.style.background = '#95a5a6';
        } else {
            this.startMonitoring();
            button.textContent = 'Stop Monitoring';
            button.style.background = '#e74c3c';
        }
    }

    // Start real-time monitoring
    async startMonitoring() {
        this.isMonitoring = true;
        
        // Start polling for real data
        this.startPolling();
        this.updateSystemStatus('online');
        this.showToast('gRPC Monitoring started');
        
        // Sync with database immediately
        await this.syncWithDatabase();
    }
    
    // Start polling for real-time updates
    startPolling() {
        if (this.pollingInterval) {
            clearInterval(this.pollingInterval);
        }
        
        this.pollingInterval = setInterval(async () => {
            if (!this.isMonitoring) return;
            
            try {
                await this.refreshMessages();
                await this.updateStats();
            } catch (error) {
                console.error('gRPC Polling error:', error);
            }
        }, 3000); // Poll every 3 seconds
    }
    
    // Comprehensive sync with gRPC database
    async syncWithDatabase() {
        console.log('Syncing with gRPC database...');
        
        try {
            // Reset local state
            this.messageHistory = [];
            
            // Load all data in parallel for faster sync
            const [messages, stats, subscribers, status] = await Promise.all([
                this.fetchFromGRPCBridge('/grpc/messages'),
                this.fetchFromGRPCBridge('/grpc/stats'),
                this.fetchFromGRPCBridge('/grpc/subscribers'),
                this.fetchFromGRPCBridge('/grpc/status')
            ]);
            
            // Update with fresh data
            if (messages && messages.messages) {
                this.updateMessagesFeed(messages.messages);
                console.log(`Loaded ${messages.messages.length} messages from gRPC database`);
            }
            
            // Update stats with real database values
            this.stats.totalMessages = stats?.totalMessages || 0;
            this.stats.activeSubscribers = stats?.activeSubscribers || 0;
            this.stats.topicsCount = stats?.topicsCount || 0;
            this.updateStatsDisplay();
            
            // Update clients list
            await this.updateClientsList();
            
            // Update system status
            this.updateSystemStatus(status?.status === 'online' ? 'online' : 'offline');
            
            console.log('gRPC Database sync completed successfully');
            console.log(`Stats: ${this.stats.totalMessages} messages, ${this.stats.topicsCount} topics, ${this.stats.activeSubscribers} subscribers`);
            
        } catch (error) {
            console.error('gRPC Database sync failed:', error);
            this.showToast('Failed to sync with gRPC database', 'error');
        }
    }
    
    // Fetch data from gRPC HTTP bridge
    async fetchFromGRPCBridge(endpoint) {
        try {
            const response = await fetch(`http://${this.brokerHost}:${this.brokerHttpBridgePort}${endpoint}`, {
                method: 'GET',
                headers: {
                    'Accept': 'application/json'
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            return await response.json();
        } catch (error) {
            console.error(`gRPC Bridge fetch error for ${endpoint}:`, error);
            throw error;
        }
    }
    
    // Refresh messages from gRPC broker
    async refreshMessages() {
        try {
            const data = await this.fetchFromGRPCBridge('/grpc/messages?limit=20');
            
            if (data && data.messages) {
                this.updateMessagesFeed(data.messages);
            }
        } catch (error) {
            console.error('Failed to refresh gRPC messages:', error);
        }
    }

    // Update messages feed with gRPC message format
    updateMessagesFeed(messages) {
        const messagesList = document.getElementById('messages-list');
        
        // Clear existing messages
        messagesList.innerHTML = '';
        
        if (!messages || messages.length === 0) {
            messagesList.innerHTML = '<div class="message-item">No messages available</div>';
            return;
        }
        
        // Store in history for filtering
        this.messageHistory = messages;
        
        // Display messages (most recent first)
        messages.slice(0, 50).forEach(msg => {
            const messageElement = this.createMessageElement(msg);
            messagesList.appendChild(messageElement);
        });
        
        this.messageCount = messages.length;
        this.updateMessageCount();
    }

    // Create message element with gRPC message format
    createMessageElement(msg) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message-item';
        
        // Convert protobuf timestamp to readable format
        const timestamp = msg.timestamp ? new Date(msg.timestamp.seconds * 1000).toLocaleString() : 'Unknown';
        
        // Convert format enum to string
        const formatMap = {
            0: 'RAW',
            1: 'JSON',
            2: 'XML'
        };
        const formatStr = formatMap[msg.format] || 'RAW';
        
        // Format content based on type
        let displayContent = msg.content;
        let contentClass = 'message-content';
        
        if (formatStr === 'JSON') {
            try {
                const parsed = JSON.parse(msg.content);
                displayContent = JSON.stringify(parsed, null, 2);
                contentClass += ' json-content';
            } catch (e) {
                // Keep original if not valid JSON
            }
        } else if (formatStr === 'XML') {
            contentClass += ' xml-content';
        }
        
        messageDiv.innerHTML = `
            <div class="message-header">
                <span class="message-topic">${this.escapeHtml(msg.topic)}</span>
                <span class="message-format format-${formatStr.toLowerCase()}">${formatStr}</span>
                <span class="message-time">${timestamp}</span>
            </div>
            <div class="${contentClass}">${this.escapeHtml(displayContent)}</div>
            ${msg.eventName ? `<div class="message-event">Event: ${this.escapeHtml(msg.eventName)}</div>` : ''}
        `;
        
        return messageDiv;
    }

    // Update system stats from gRPC
    async updateStats() {
        try {
            const stats = await this.fetchFromGRPCBridge('/grpc/stats');
            
            if (stats) {
                this.stats.totalMessages = stats.totalMessages || 0;
                this.stats.activeSubscribers = stats.activeSubscribers || 0;
                this.stats.topicsCount = stats.topicsCount || 0;
                this.stats.messagesPerMinute = stats.messagesPerMinute || 0;
                
                this.updateStatsDisplay();
            }
        } catch (error) {
            console.error('Failed to update gRPC stats:', error);
        }
    }

    // Get broker status from gRPC
    async getBrokerStatus() {
        try {
            const status = await this.fetchFromGRPCBridge('/grpc/status');
            
            if (status) {
                this.updateSystemStatus(status.status === 'online' ? 'online' : 'offline');
                
                // Update RAFT information if available
                if (status.raftStatus) {
                    this.updateRaftStatus(status.raftStatus);
                }
            }
        } catch (error) {
            console.error('Failed to get gRPC broker status:', error);
            this.updateSystemStatus('offline');
        }
    }

    // Update RAFT status display
    updateRaftStatus(raftStatus) {
        const raftElement = document.getElementById('raft-status');
        if (raftElement) {
            const stateMap = {
                0: 'FOLLOWER',
                1: 'CANDIDATE', 
                2: 'LEADER'
            };
            
            const state = stateMap[raftStatus.state] || 'UNKNOWN';
            const term = raftStatus.currentTerm || 0;
            const leaderId = raftStatus.leaderId || 'None';
            
            raftElement.innerHTML = `
                <h4> RAFT Consensus</h4>
                <div>State: <span class="raft-state-${state.toLowerCase()}">${state}</span></div>
                <div>Term: ${term}</div>
                <div>Leader: ${leaderId}</div>
                <div>Nodes: ${raftStatus.clusterNodes ? raftStatus.clusterNodes.length : 0}</div>
            `;
        }
    }

    // Update clients list from gRPC
    async updateClientsList() {
        try {
            const data = await this.fetchFromGRPCBridge('/grpc/subscribers');
            
            const clientsList = document.getElementById('clients-list');
            
            if (!data || !data.subscribers || data.subscribers.length === 0) {
                clientsList.innerHTML = '<div class="client-item">No active subscribers</div>';
                return;
            }
            
            clientsList.innerHTML = '';
            
            data.subscribers.forEach(subscriber => {
                const clientDiv = document.createElement('div');
                clientDiv.className = 'client-item';
                
                const lastSeen = subscriber.lastSeen ? 
                    new Date(subscriber.lastSeen.seconds * 1000).toLocaleString() : 'Unknown';
                
                const topics = subscriber.topics ? subscriber.topics.join(', ') : 'None';
                
                clientDiv.innerHTML = `
                    <div class="client-header">
                        <span class="client-id">${this.escapeHtml(subscriber.id)}</span>
                        <span class="client-status ${subscriber.isActive ? 'active' : 'inactive'}">
                            ${subscriber.isActive ? 'ACTIVE' : 'INACTIVE'}
                        </span>
                    </div>
                    <div class="client-details">
                        <div>Topics: ${this.escapeHtml(topics)}</div>
                        <div>Last Seen: ${lastSeen}</div>
                        <div>Role: ${this.escapeHtml(subscriber.role)}</div>
                    </div>
                `;
                
                clientsList.appendChild(clientDiv);
            });
            
        } catch (error) {
            console.error('Failed to update gRPC clients list:', error);
        }
    }

    // Stop monitoring
    stopMonitoring() {
        this.isMonitoring = false;
        if (this.pollingInterval) {
            clearInterval(this.pollingInterval);
        }
        this.updateSystemStatus('offline');
        this.showToast('gRPC Monitoring stopped');
    }

    // Clear messages display
    clearMessages() {
        document.getElementById('messages-list').innerHTML = '';
        this.messageHistory = [];
        this.messageCount = 0;
        this.updateMessageCount();
        this.showToast('Messages cleared');
    }

    // Filter messages by topic
    filterMessages(filterTopic) {
        const messagesList = document.getElementById('messages-list');
        const messages = messagesList.querySelectorAll('.message-item');
        
        messages.forEach(messageElement => {
            const topicElement = messageElement.querySelector('.message-topic');
            if (topicElement) {
                const topic = topicElement.textContent.toLowerCase();
                const shouldShow = !filterTopic || topic.includes(filterTopic.toLowerCase());
                messageElement.style.display = shouldShow ? 'block' : 'none';
            }
        });
    }

    // Update stats display
    updateStatsDisplay() {
        document.getElementById('total-messages').textContent = this.stats.totalMessages;
        document.getElementById('active-subscribers').textContent = this.stats.activeSubscribers;
        document.getElementById('topics-count').textContent = this.stats.topicsCount;
        document.getElementById('messages-per-minute').textContent = this.stats.messagesPerMinute.toFixed(1);
    }

    // Update message count
    updateMessageCount() {
        document.getElementById('message-count').textContent = this.messageCount;
    }

    // Update system status
    updateSystemStatus(status) {
        const statusElement = document.getElementById('system-status');
        const statusIndicator = document.getElementById('status-indicator');
        
        if (status === 'online') {
            statusElement.textContent = 'gRPC Broker Online';
            statusElement.className = 'status online';
            statusIndicator.textContent = 'ACTIVE';
        } else {
            statusElement.textContent = 'gRPC Broker Offline';
            statusElement.className = 'status offline';
            statusIndicator.textContent = 'INACTIVE';
        }
    }

    // Update last seen timestamp
    updateLastSeen() {
        document.getElementById('last-updated').textContent = new Date().toLocaleTimeString();
    }

    // Start health check
    startHealthCheck() {
        setInterval(async () => {
            try {
                await this.getBrokerStatus();
            } catch (error) {
                this.updateSystemStatus('offline');
            }
        }, 10000); // Check every 10 seconds
    }

    // Show toast notification
    showToast(message, type = 'success') {
        // Create toast element
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        
        // Add to page
        document.body.appendChild(toast);
        
        // Show toast
        setTimeout(() => toast.classList.add('show'), 100);
        
        // Remove toast after 3 seconds
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => document.body.removeChild(toast), 300);
        }, 3000);
    }

    // Escape HTML to prevent XSS
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize dashboard when page loads
document.addEventListener('DOMContentLoaded', () => {
    new MessageBrokerDashboardGRPC();
});

// Add toast styles
const toastStyles = `
.toast {
    position: fixed;
    top: 20px;
    right: 20px;
    padding: 12px 24px;
    border-radius: 4px;
    color: white;
    font-weight: bold;
    transform: translateX(400px);
    transition: transform 0.3s ease;
    z-index: 1000;
}

.toast.show {
    transform: translateX(0);
}

.toast-success {
    background-color: #28a745;
}

.toast-error {
    background-color: #dc3545;
}

.toast-info {
    background-color: #17a2b8;
}

.raft-state-leader {
    color: #28a745;
    font-weight: bold;
}

.raft-state-candidate {
    color: #ffc107;
    font-weight: bold;
}

.raft-state-follower {
    color: #6c757d;
    font-weight: bold;
}

.message-content.json-content {
    font-family: 'Courier New', monospace;
    background-color: #f8f9fa;
    padding: 8px;
    border-radius: 4px;
    white-space: pre-wrap;
}

.message-content.xml-content {
    font-family: 'Courier New', monospace;
    background-color: #fff3cd;
    padding: 8px;
    border-radius: 4px;
}

.client-status.active {
    color: #28a745;
}

.client-status.inactive {
    color: #dc3545;
}
`;

// Add styles to page
const styleSheet = document.createElement('style');
styleSheet.textContent = toastStyles;
document.head.appendChild(styleSheet);