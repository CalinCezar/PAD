using System.Net.Sockets;
using System.Text;
using System.Xml.Serialization;
using Newtonsoft.Json;

namespace Publisher;

class Publisher
{
	private static string host = "127.0.0.1";
	private static int port = 5000;

	public static void Main()
	{
		SendMessages();
	}

	public static void SendMessages()
	{
		try
		{
			using (TcpClient client = new TcpClient(host, port))
			using (NetworkStream stream = client.GetStream())
			{
				Console.WriteLine("Publisher connected to broker.");
				Console.WriteLine("Type messages to send (type 'exit' to quit):");

				while (true)
				{
					Console.Write("Enter value: ");
					string value = Console.ReadLine();

					if (string.IsNullOrWhiteSpace(value))
						continue;

					if (value.ToLower() == "exit")
						break;

					Console.Write("Enter topic: ");
					string topic = Console.ReadLine();
					if (string.IsNullOrWhiteSpace(topic))
						topic = "news"; // default topic

					Console.Write("Enter format (json/xml): ");
					string format = Console.ReadLine()?.ToLower();
					if (format != "json" && format != "xml")
						format = "json"; // default format

					Message message = new Message
					{
						Id = DateTime.Now.Ticks,
						EventName = "ManualEvent",
						Value = value,
						Topic = topic
					};

					string dataToSend = "";

					if (format == "json")
					{
						dataToSend = "FORMAT:JSON|" + JsonConvert.SerializeObject(message) + "\n";
					}
					else if (format == "xml")
					{
						XmlSerializer serializer = new XmlSerializer(typeof(Message));
						using (StringWriter writer = new StringWriter())
						{
							serializer.Serialize(writer, message);
							// compact XML pe o singură linie
							string xmlString = writer.ToString()
							    .Replace("\r", "")
							    .Replace("\n", "")
							    .Replace("  ", "");
							dataToSend = "FORMAT:XML|" + xmlString + "\n";
						}
					}

					byte[] data = Encoding.UTF8.GetBytes(dataToSend);
					stream.Write(data, 0, data.Length);

					Console.WriteLine($"Publisher sent message to topic '{topic}' in {format.ToUpper()} format.");
				}
			}
		}
		catch (Exception ex)
		{
			Console.WriteLine("Publisher error: " + ex.Message);
		}
	}
}