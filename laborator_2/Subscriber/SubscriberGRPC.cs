using Grpc.Net.Client;
using Grpc.Core;
using Newtonsoft.Json;
using System.Text;
using System.Xml.Serialization;
using Broker;
using Google.Protobuf.WellKnownTypes;

namespace Subscriber;

[Serializable]
public class Message
{
	public long Id { get; set; }
	public string EventName { get; set; } = string.Empty;
	public string Value { get; set; } = string.Empty;
	public string Topic { get; set; } = string.Empty;
}

public class ClusterNode
{
	public string Host { get; set; } = string.Empty;
	public int GrpcPort { get; set; }
	public int HttpPort { get; set; }
	public string Name { get; set; } = string.Empty;
	public bool IsLeader { get; set; }
	public bool IsAvailable { get; set; } = true;
	
	public ClusterNode(string host, int grpcPort, int httpPort, string name)
	{
		Host = host;
		GrpcPort = grpcPort;
		HttpPort = httpPort;
		Name = name;
	}
	
	public string GrpcAddress => $"{Host}:{GrpcPort}";
	public string HttpUrl => $"http://{Host}:{HttpPort}";
	
	public override string ToString()
	{
		var status = IsLeader ? " [LEADER]" : "";
		status += IsAvailable ? " [ONLINE]" : " [OFFLINE]";
		return $"{Name} (gRPC:{GrpcAddress}){status}";
	}
}

class SubscriberGRPC
{
	private static string host = Environment.GetEnvironmentVariable("BROKER_HOST") ?? "127.0.0.1";
	private static int port = int.Parse(Environment.GetEnvironmentVariable("BROKER_PORT") ?? "50051");
	private static bool useCluster = false;
	private static List<ClusterNode> clusterNodes = new List<ClusterNode>();
	private static ClusterNode? currentNode = null;
	private static GrpcChannel? channel = null;
	private static SubscriberService.SubscriberServiceClient? subscriberClient = null;
	private static DashboardService.DashboardServiceClient? dashboardClient = null;

	public static async Task Main(string[] args)
	{
		Console.WriteLine(" Starting gRPC Message Subscriber...");
		
		// Check for cluster mode argument
		useCluster = args.Length > 0 && args[0].Equals("cluster", StringComparison.OrdinalIgnoreCase);
		
		if (useCluster)
		{
			InitializeCluster();
			Console.WriteLine(" gRPC Cluster mode enabled with " + clusterNodes.Count + " nodes");
		}
		else
		{
			Console.WriteLine(" Single node mode");
		}
		
		var topics = new List<string>();
		
		// Check if running in Docker (environment variable set)
		if (!string.IsNullOrEmpty(Environment.GetEnvironmentVariable("BROKER_HOST")))
		{
			// Running in Docker - auto-subscribe to default topics
			topics.Add("news");
			topics.Add("alerts");
			Console.WriteLine("Docker mode: Auto-subscribing to topics: news, alerts");
		}
		else
		{
			// Interactive mode
			Console.WriteLine("Enter topics to subscribe (comma separated, e.g., news,alerts):");
			string? input = Console.ReadLine();
			
			if (!string.IsNullOrWhiteSpace(input))
			{
				foreach (var t in input.Split(','))
				{
					string topic = t.Trim();
					if (!string.IsNullOrEmpty(topic))
						topics.Add(topic);
				}
			}
		}

		await StartSubscriber(topics);
	}
	
	private static void InitializeCluster()
	{
		// Add cluster nodes (gRPC ports: 50051, 50052, 50053)
		clusterNodes.Add(new ClusterNode("127.0.0.1", 50051, 8080, "Node 0"));
		clusterNodes.Add(new ClusterNode("127.0.0.1", 50052, 8081, "Node 1"));
		clusterNodes.Add(new ClusterNode("127.0.0.1", 50053, 8082, "Node 2"));
		
		UpdateClusterStatus();
	}
	
	private static void UpdateClusterStatus()
	{
		Console.WriteLine(" Checking gRPC cluster status...");
		
		foreach (var node in clusterNodes)
		{
			try
			{
				// Create temporary channel to test connection
				using var testChannel = GrpcChannel.ForAddress($"http://{node.GrpcAddress}");
				var testClient = new DashboardService.DashboardServiceClient(testChannel);
				
				// Test with timeout
				using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(2));
				var status = testClient.GetBrokerStatus(new Empty(), 
					deadline: DateTime.UtcNow.AddSeconds(2));
				
				node.IsAvailable = true;
				bool isLeader = status.RaftStatus.State == NodeState.Leader;
				node.IsLeader = isLeader;
				
				if (isLeader)
				{
					Console.WriteLine($" Found gRPC leader: {node}");
				}
				else
				{
					Console.WriteLine($" Available gRPC node: {node}");
				}
			}
			catch (Exception e)
			{
				node.IsAvailable = false;
				node.IsLeader = false;
				Console.WriteLine($" Unreachable gRPC node: {node} ({e.Message})");
			}
		}
	}
	
	private static ClusterNode? FindBestNode()
	{
		// Update cluster status first
		UpdateClusterStatus();
		
		// Prefer leader nodes
		foreach (var node in clusterNodes)
		{
			if (node.IsAvailable && node.IsLeader)
			{
				Console.WriteLine($" Selecting gRPC leader node: {node}");
				return node;
			}
		}
		
		// Fallback to any available node
		foreach (var node in clusterNodes)
		{
			if (node.IsAvailable)
			{
				Console.WriteLine($"[INFO] Selecting available gRPC node: {node}");
				return node;
			}
		}
		
		Console.WriteLine(" No available gRPC nodes found, trying first node as fallback");
		return clusterNodes.Count > 0 ? clusterNodes[0] : null;
	}

	public static async Task StartSubscriber(List<string> topics)
	{
		while (true)
		{
			try
			{
				string connectHost;
				int connectPort;
				
				if (useCluster)
				{
					var targetNode = FindBestNode();
					if (targetNode == null)
					{
						Console.WriteLine(" No available nodes in cluster. Retrying in 5 seconds...");
						await Task.Delay(5000);
						continue;
					}
					
					currentNode = targetNode;
					connectHost = targetNode.Host;
					connectPort = targetNode.GrpcPort;
				}
				else
				{
					connectHost = host;
					connectPort = port;
				}
				
				string serverAddress = $"http://{connectHost}:{connectPort}";
				Console.WriteLine($" Connecting to gRPC broker at {serverAddress}...");
				
				// Create gRPC channel
				channel = GrpcChannel.ForAddress(serverAddress, new GrpcChannelOptions
				{
					HttpHandler = new SocketsHttpHandler
					{
						PooledConnectionIdleTimeout = Timeout.InfiniteTimeSpan,
						KeepAlivePingDelay = TimeSpan.FromSeconds(60),
						KeepAlivePingTimeout = TimeSpan.FromSeconds(30),
						EnableMultipleHttp2Connections = true
					}
				});
				
				// Create service clients
				subscriberClient = new SubscriberService.SubscriberServiceClient(channel);
				dashboardClient = new DashboardService.DashboardServiceClient(channel);
				
				// Test connection
				try
				{
					var status = dashboardClient.GetBrokerStatus(new Empty(),
						deadline: DateTime.UtcNow.AddSeconds(5));
					Console.WriteLine($" Connected to gRPC broker! Status: {status.Status}");
					
					if (useCluster && currentNode != null)
					{
						Console.WriteLine($" Connected to cluster node: {currentNode}");
					}
				}
				catch (RpcException e)
				{
					Console.WriteLine($" Failed to connect to broker: {e.Status}");
					throw;
				}
				
				// Subscribe to topics
				await SubscribeToTopics(topics);
				
			}
			catch (Exception e)
			{
				Console.WriteLine($" Connection failed: {e.Message}");
				
				// Clean up
				if (channel != null)
				{
					await channel.ShutdownAsync();
					channel.Dispose();
					channel = null;
				}
				
				subscriberClient = null;
				dashboardClient = null;
				
				if (useCluster)
				{
					Console.WriteLine("[INFO] Trying to reconnect to cluster in 5 seconds...");
					await Task.Delay(5000);
				}
				else
				{
					Console.WriteLine("[INFO] Trying to reconnect in 5 seconds...");
					await Task.Delay(5000);
				}
			}
		}
	}
	
	private static async Task SubscribeToTopics(List<string> topics)
	{
		if (subscriberClient == null)
		{
			throw new InvalidOperationException("Subscriber client not initialized");
		}
		
		Console.WriteLine($"📚 Subscribing to topics: {string.Join(", ", topics)}");
		
		// Create subscription request
		var subscribeRequest = new SubscribeRequest
		{
			SubscriberId = $"csharp_subscriber_{Environment.MachineName}_{DateTime.Now:yyyyMMdd_HHmmss}",
			IncludeHistorical = true
		};
		
		subscribeRequest.Topics.AddRange(topics);
		subscribeRequest.Formats.AddRange(new[] { MessageFormat.Raw, MessageFormat.Json, MessageFormat.Xml });
		
		Console.WriteLine($"🆔 Subscriber ID: {subscribeRequest.SubscriberId}");
		
		// Start heartbeat task
		var heartbeatCts = new CancellationTokenSource();
		var heartbeatTask = StartHeartbeat(subscribeRequest.SubscriberId, heartbeatCts.Token);
		
		try
		{
			// Subscribe and listen for messages
			using var call = subscriberClient.Subscribe(subscribeRequest);
			
			Console.WriteLine(" Successfully subscribed! Listening for messages...");
			Console.WriteLine("Press Ctrl+C to stop.");
			
			await foreach (var message in call.ResponseStream.ReadAllAsync())
			{
				await ProcessMessage(message);
			}
		}
		catch (RpcException e) when (e.StatusCode == StatusCode.Cancelled)
		{
			Console.WriteLine(" Subscription cancelled");
		}
		catch (RpcException e)
		{
			Console.WriteLine($" gRPC error during subscription: {e.Status}");
			throw;
		}
		finally
		{
			// Stop heartbeat
			heartbeatCts.Cancel();
			try
			{
				await heartbeatTask;
			}
			catch (OperationCanceledException)
			{
				// Expected when cancelling
			}
		}
	}
	
	private static async Task StartHeartbeat(string subscriberId, CancellationToken cancellationToken)
	{
		if (subscriberClient == null) return;
		
		try
		{
			while (!cancellationToken.IsCancellationRequested)
			{
				try
				{
					var heartbeatRequest = new HeartbeatRequest
					{
						SubscriberId = subscriberId,
						Timestamp = Timestamp.FromDateTime(DateTime.UtcNow)
					};
					
					var response = subscriberClient.Heartbeat(heartbeatRequest,
						deadline: DateTime.UtcNow.AddSeconds(5));
					
					// Console.WriteLine($"💓 Heartbeat acknowledged at {response.ServerTimestamp.ToDateTime():HH:mm:ss}");
				}
				catch (RpcException e)
				{
					Console.WriteLine($"Heartbeat failed: {e.Status.Detail}");
				}
				
				await Task.Delay(30000, cancellationToken); // Heartbeat every 30 seconds
			}
		}
		catch (OperationCanceledException)
		{
			// Expected when cancelled
		}
	}
	
	private static async Task ProcessMessage(Broker.Message message)
	{
		try
		{
			string timestamp = message.Timestamp.ToDateTime().ToString("yyyy-MM-dd HH:mm:ss");
			string formatStr = message.Format.ToString().ToUpper();
			
			Console.WriteLine($"\n📩 New Message Received:");
			Console.WriteLine($"    Topic: {message.Topic}");
			Console.WriteLine($"    Format: {formatStr}");
			Console.WriteLine($"   🕒 Time: {timestamp}");
			Console.WriteLine($"    Event: {message.EventName}");
			Console.WriteLine($"    Content:");
			
			// Process based on format
			switch (message.Format)
			{
				case MessageFormat.Json:
					await ProcessJsonMessage(message.Content);
					break;
					
				case MessageFormat.Xml:
					await ProcessXmlMessage(message.Content);
					break;
					
				case MessageFormat.Raw:
				default:
					Console.WriteLine($"      {message.Content}");
					break;
			}
			
			Console.WriteLine("   ─────────────────────");
		}
		catch (Exception e)
		{
			Console.WriteLine($" Error processing message: {e.Message}");
		}
	}
	
	private static async Task ProcessJsonMessage(string content)
	{
		try
		{
			// Try to parse and pretty-print JSON
			var jsonObject = JsonConvert.DeserializeObject(content);
			string prettyJson = JsonConvert.SerializeObject(jsonObject, Formatting.Indented);
			
			// Indent each line
			var lines = prettyJson.Split('\n');
			foreach (var line in lines)
			{
				Console.WriteLine($"      {line}");
			}
			
			// Try to extract structured data
			if (jsonObject is Newtonsoft.Json.Linq.JObject jObj)
			{
				if (jObj.ContainsKey("Id"))
					Console.WriteLine($"   🆔 Message ID: {jObj["Id"]}");
				if (jObj.ContainsKey("EventName"))
					Console.WriteLine($"   🎪 Event Name: {jObj["EventName"]}");
				if (jObj.ContainsKey("Value"))
					Console.WriteLine($"   💎 Value: {jObj["Value"]}");
			}
		}
		catch (JsonException)
		{
			// If not valid JSON, just display as text
			Console.WriteLine($"      {content}");
		}
		
		await Task.CompletedTask;
	}
	
	private static async Task ProcessXmlMessage(string content)
	{
		try
		{
			// Try to parse XML and extract information
			var xmlDoc = new System.Xml.XmlDocument();
			xmlDoc.LoadXml(content);
			
			// Pretty print XML (simple indentation)
			var lines = content.Split('\n');
			foreach (var line in lines)
			{
				Console.WriteLine($"      {line.Trim()}");
			}
			
			// Try to extract structured data from XML
			var idNode = xmlDoc.SelectSingleNode("//Id");
			var eventNameNode = xmlDoc.SelectSingleNode("//EventName");
			var valueNode = xmlDoc.SelectSingleNode("//Value");
			var topicNode = xmlDoc.SelectSingleNode("//Topic");
			
			if (idNode != null)
				Console.WriteLine($"   🆔 Message ID: {idNode.InnerText}");
			if (eventNameNode != null)
				Console.WriteLine($"   🎪 Event Name: {eventNameNode.InnerText}");
			if (valueNode != null)
				Console.WriteLine($"   💎 Value: {valueNode.InnerText}");
			if (topicNode != null)
				Console.WriteLine($"    Topic: {topicNode.InnerText}");
		}
		catch (System.Xml.XmlException)
		{
			// If not valid XML, just display as text
			Console.WriteLine($"      {content}");
		}
		
		await Task.CompletedTask;
	}
}