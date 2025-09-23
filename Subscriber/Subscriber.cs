using Newtonsoft.Json;
using System.Net.Sockets;
using System.Text;
using System.Xml.Serialization;
using System.Net.Http;

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
	public int TcpPort { get; set; }
	public int HttpPort { get; set; }
	public string Name { get; set; } = string.Empty;
	public bool IsLeader { get; set; }
	public bool IsAvailable { get; set; } = true;
	
	public ClusterNode(string host, int tcpPort, int httpPort, string name)
	{
		Host = host;
		TcpPort = tcpPort;
		HttpPort = httpPort;
		Name = name;
	}
	
	public string HttpUrl => $"http://{Host}:{HttpPort}";
	public string ConnectionString => $"{Host}:{TcpPort}";
	
	public override string ToString()
	{
		var status = IsLeader ? " [LEADER]" : "";
		status += IsAvailable ? " [ONLINE]" : " [OFFLINE]";
		return $"{Name} ({ConnectionString}){status}";
	}
}

class Subscriber
{
	private static string host = Environment.GetEnvironmentVariable("BROKER_HOST") ?? "127.0.0.1";
	private static int port = int.Parse(Environment.GetEnvironmentVariable("BROKER_PORT") ?? "5000");
	private static bool useCluster = false;
	private static List<ClusterNode> clusterNodes = new List<ClusterNode>();
	private static ClusterNode? currentNode = null;

	public static void Main(string[] args)
	{
		// Check for cluster mode argument
		useCluster = args.Length > 0 && args[0].Equals("cluster", StringComparison.OrdinalIgnoreCase);
		
		if (useCluster)
		{
			InitializeCluster();
			Console.WriteLine("🌐 Cluster mode enabled with " + clusterNodes.Count + " nodes");
		}
		else
		{
			Console.WriteLine("📡 Single node mode");
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

		StartSubscriber(topics);
	}
	
	private static void InitializeCluster()
	{
		// Add cluster nodes (matches the cluster configuration)
		clusterNodes.Add(new ClusterNode("127.0.0.1", 5000, 8080, "Node 0"));
		clusterNodes.Add(new ClusterNode("127.0.0.1", 5001, 8081, "Node 1"));
		clusterNodes.Add(new ClusterNode("127.0.0.1", 5002, 8082, "Node 2"));
		
		UpdateClusterStatus();
	}
	
	private static void UpdateClusterStatus()
	{
		Console.WriteLine("🔍 Checking cluster status...");
		
		using (var httpClient = new HttpClient())
		{
			httpClient.Timeout = TimeSpan.FromSeconds(2);
			
			foreach (var node in clusterNodes)
			{
				try
				{
					var response = httpClient.GetAsync(node.HttpUrl + "/raft").Result;
					if (response.IsSuccessStatusCode)
					{
						var content = response.Content.ReadAsStringAsync().Result;
						
						// Simple JSON parsing for state
						bool isLeader = content.Contains("\"state\":\"LEADER\"") || 
									   content.Contains("\"state\": \"LEADER\"");
						
						node.IsAvailable = true;
						node.IsLeader = isLeader;
						
						if (isLeader)
						{
							Console.WriteLine($"👑 Found leader: {node}");
						}
						else
						{
							Console.WriteLine($"📡 Available node: {node}");
						}
					}
					else
					{
						node.IsAvailable = false;
						node.IsLeader = false;
						Console.WriteLine($"❌ Unavailable node: {node}");
					}
				}
				catch (Exception e)
				{
					node.IsAvailable = false;
					node.IsLeader = false;
					Console.WriteLine($"❌ Unreachable node: {node} ({e.Message})");
				}
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
				Console.WriteLine($"🎯 Selecting leader node: {node}");
				return node;
			}
		}
		
		// Fallback to any available node
		foreach (var node in clusterNodes)
		{
			if (node.IsAvailable)
			{
				Console.WriteLine($"🔄 Selecting available node: {node}");
				return node;
			}
		}
		
		Console.WriteLine("⚠️  No available nodes found, trying first node as fallback");
		return clusterNodes.Count > 0 ? clusterNodes[0] : null;
	}

	public static void StartSubscriber(List<string> topics)
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
						Console.WriteLine("❌ No cluster nodes available, waiting 5 seconds...");
						Thread.Sleep(5000);
						continue;
					}
					
					connectHost = targetNode.Host;
					connectPort = targetNode.TcpPort;
					currentNode = targetNode;
					Console.WriteLine($"🌐 Connecting to cluster via {targetNode}");
				}
				else
				{
					connectHost = host;
					connectPort = port;
					Console.WriteLine($"📡 Connecting to single node {connectHost}:{connectPort}");
				}
				
				Console.WriteLine("Attempting to connect to broker...");
				using (TcpClient client = new TcpClient(connectHost, connectPort))
				{
					NetworkStream stream = client.GetStream();

					// Send role identification first
					byte[] roleData = Encoding.UTF8.GetBytes("SUBSCRI");
					stream.Write(roleData, 0, roleData.Length);

					// Give the broker time to process the role
					Thread.Sleep(100);

					// Send subscription messages
					foreach (var topic in topics)
					{
						string subscribeMessage = "SUBSCRIBE:" + topic + "\n";
						byte[] data = Encoding.UTF8.GetBytes(subscribeMessage);
						stream.Write(data, 0, data.Length);
						Console.WriteLine($"Subscribed to topic '{topic}'");
					}

					// Give time for subscriptions to be processed
					Thread.Sleep(100);

					// Start heartbeat timer (ping every 30 seconds)
					Timer heartbeatTimer = new Timer(state =>
					{
						try
						{
							byte[] pingData = Encoding.UTF8.GetBytes("PING\n");
							stream.Write(pingData, 0, pingData.Length);
						}
						catch (Exception ex)
						{
							Console.WriteLine($"Heartbeat failed: {ex.Message}");
						}
					}, null, TimeSpan.FromSeconds(30), TimeSpan.FromSeconds(30));

					try
					{
						using (StreamReader reader = new StreamReader(stream))
						{
						while (true)
						{
							string? message = reader.ReadLine();
							if (message == null)
								break;
								
							if (message == "PONG")
								{
									continue;
								}
								else if (message.StartsWith("FORMAT:JSON"))
								{
									try
									{
										string jsonMessage = message.Split('|')[1];
										Message msg = JsonConvert.DeserializeObject<Message>(jsonMessage);
										Console.WriteLine($"[JSON][{msg.Topic}] {msg.Value}");
									}
									catch (JsonException ex)
									{
										Console.WriteLine($"[JSON] Parse error: {ex.Message}");
										Console.WriteLine($"[JSON] Raw message: {message}");
									}
								}
								else if (message.StartsWith("FORMAT:XML"))
								{
									try
									{
										string? xmlMessage = message.Split('|').Length > 1 ? message.Split('|')[1] : null;
										if (xmlMessage != null)
										{
											Message? msg = DeserializeXml<Message>(xmlMessage);
											if (msg != null)
												Console.WriteLine($"[XML][{msg.Topic}] {msg.Value}");
										}
									}
									catch (Exception ex)
									{
										Console.WriteLine($"[XML] Parse error: {ex.Message}");
										Console.WriteLine($"[XML] Raw message: {message}");
									}
								}
								else
								{
									Console.WriteLine("[RAW] " + message);
								}
							}
						}
					}
					finally
					{
						// Clean up timer
						heartbeatTimer?.Dispose();
					}
				}
			}
			catch (Exception ex)
			{
				Console.WriteLine($"❌ Connection error: {ex.Message}");
				
				if (useCluster)
				{
					Console.WriteLine("🔄 Trying to reconnect to cluster in 5 seconds...");
				}
				else
				{
					Console.WriteLine("🔄 Trying to reconnect in 5 seconds...");
				}
				
				Thread.Sleep(5000);
			}
		}
	}

	// Deserializare XML
	public static T? DeserializeXml<T>(string xml) where T : class
	{
		XmlSerializer serializer = new XmlSerializer(typeof(T));
		using (StringReader reader = new StringReader(xml))
		{
			return (T?)serializer.Deserialize(reader);
		}
	}
}