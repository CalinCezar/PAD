using Newtonsoft.Json;
using System.Net.Sockets;
using System.Text;
using System.Xml.Serialization;

namespace Subscriber;

[Serializable]
public class Message
{
	public long Id { get; set; }
	public string EventName { get; set; } = string.Empty;
	public string Value { get; set; } = string.Empty;
	public string Topic { get; set; } = string.Empty;
}

class Subscriber
{
	private static string host = Environment.GetEnvironmentVariable("BROKER_HOST") ?? "127.0.0.1";
	private static int port = int.Parse(Environment.GetEnvironmentVariable("BROKER_PORT") ?? "5000");

	public static void Main()
	{
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

	public static void StartSubscriber(List<string> topics)
	{
		while (true)
		{
			try
			{
				Console.WriteLine("Attempting to connect to broker...");
				using (TcpClient client = new TcpClient(host, port))
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
				Console.WriteLine($"Connection lost: {ex.Message}. Trying to reconnect...");
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