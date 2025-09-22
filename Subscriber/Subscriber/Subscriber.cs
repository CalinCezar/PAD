using Newtonsoft.Json;
using System.Net.Sockets;
using System.Text;
using System.Xml.Serialization;

namespace Subscriber;

class Subscriber
{
	private static string host = "127.0.0.1";
	private static int port = 5000;

	public static void Main()
	{
		Console.WriteLine("Enter topics to subscribe (comma separated, e.g., news,alerts):");
		string input = Console.ReadLine();
		var topics = new List<string>();

		if (!string.IsNullOrWhiteSpace(input))
		{
			foreach (var t in input.Split(','))
			{
				string topic = t.Trim();
				if (!string.IsNullOrEmpty(topic))
					topics.Add(topic);
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

					foreach (var topic in topics)
					{
						string subscribeMessage = "SUBSCRIBE:" + topic + "\n";
						byte[] data = Encoding.UTF8.GetBytes(subscribeMessage);
						stream.Write(data, 0, data.Length);
						Console.WriteLine($"Subscribed to topic '{topic}'");
					}

					using (StreamReader reader = new StreamReader(stream))
					{
						while (true)
						{
							string message = reader.ReadLine();
							if (message == null)
								break;

							if (message.StartsWith("FORMAT:JSON"))
							{
								string jsonMessage = message.Split('|')[1];
								Message msg = JsonConvert.DeserializeObject<Message>(jsonMessage);
								Console.WriteLine($"[JSON][{msg.Topic}] {msg.Value}");
							}
							else if (message.StartsWith("FORMAT:XML"))
							{
								string xmlMessage = message.Split('|')[1];
								Message msg = DeserializeXml<Message>(xmlMessage);
								Console.WriteLine($"[XML][{msg.Topic}] {msg.Value}");
							}
							else
							{
								Console.WriteLine("[RAW] " + message);
							}
						}
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
	public static T DeserializeXml<T>(string xml)
	{
		XmlSerializer serializer = new XmlSerializer(typeof(T));
		using (StringReader reader = new StringReader(xml))
		{
			return (T)serializer.Deserialize(reader);
		}
	}
}
