using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Collections.Concurrent;
using Newtonsoft.Json;
using System.Xml.Serialization;

namespace Broker;

class Broker
{
	private static string host = "127.0.0.1";
	private static int port = 5000;

	// subscriberii organizați pe topic
	private static ConcurrentDictionary<string, List<NetworkStream>> subscribers
	    = new ConcurrentDictionary<string, List<NetworkStream>>();

	public static void Main()
	{
		StartBroker();
	}

	public static void StartBroker()
	{
		TcpListener listener = new TcpListener(IPAddress.Parse(host), port);
		listener.Start();

		Console.WriteLine($"Broker started. Waiting for connections on {host}:{port}");

		while (true)
		{
			TcpClient client = listener.AcceptTcpClient();
			Console.WriteLine("Client connected.");

			Thread t = new Thread(() => HandleClient(client));
			t.Start();
		}
	}

	private static void HandleClient(TcpClient client)
	{
		try
		{
			NetworkStream stream = client.GetStream();
			StreamReader reader = new StreamReader(stream);

			// prima linie = SUBSCRIBE sau mesaje de la publisher
			string firstLine = reader.ReadLine();

			if (firstLine != null && firstLine.StartsWith("SUBSCRIBE:"))
			{
				string topic = firstLine.Split(':')[1].Trim();

				subscribers.AddOrUpdate(topic,
				    new List<NetworkStream> { stream },
				    (key, list) => { list.Add(stream); return list; });

				Console.WriteLine($"New subscriber for topic '{topic}'");

				// ascultă doar pentru menținerea conexiunii
				while (client.Connected) Thread.Sleep(1000);
			}
			else
			{
				// este un publisher → continuă să trimită mesaje
				if (!string.IsNullOrEmpty(firstLine))
				{
					ProcessPublisherMessage(firstLine);
				}

				while (true)
				{
					string message = reader.ReadLine();
					if (string.IsNullOrEmpty(message)) break;

					ProcessPublisherMessage(message);
				}
			}
		}
		catch (Exception ex)
		{
			Console.WriteLine("Broker error: " + ex.Message);
		}
	}

	private static void ProcessPublisherMessage(string message)
	{
		if (message.StartsWith("FORMAT:JSON"))
		{
			string jsonMessage = message.Split('|')[1];
			dynamic msg = JsonConvert.DeserializeObject(jsonMessage);

			string topic = msg.Topic ?? "default";
			Console.WriteLine($"Broker received JSON message for topic '{topic}': {jsonMessage}");

			if (subscribers.ContainsKey(topic))
			{
				foreach (var subStream in subscribers[topic])
				{
					if (subStream.CanWrite)
					{
						byte[] data = Encoding.UTF8.GetBytes("FORMAT:JSON|" + jsonMessage + "\n");
						subStream.Write(data, 0, data.Length);
					}
				}
			}
		}
		else if (message.StartsWith("FORMAT:XML"))
		{
			string xmlMessage = message.Split('|')[1];
			string topic = ExtractTopicFromXml(xmlMessage) ?? "default";

			Console.WriteLine($"Broker received XML message for topic '{topic}': {xmlMessage}");

			if (subscribers.ContainsKey(topic))
			{
				foreach (var subStream in subscribers[topic])
				{
					if (subStream.CanWrite)
					{
						byte[] data = Encoding.UTF8.GetBytes("FORMAT:XML|" + xmlMessage + "\n");
						subStream.Write(data, 0, data.Length);
					}
				}
			}
		}
	}

	// Metodă pentru a extrage topicul din XML
	private static string ExtractTopicFromXml(string xml)
	{
		try
		{
			var serializer = new XmlSerializer(typeof(Message));
			using (var reader = new StringReader(xml))
			{
				var msg = (Message)serializer.Deserialize(reader);
				return msg.Topic;
			}
		}
		catch
		{
			return null;
		}
	}
}
