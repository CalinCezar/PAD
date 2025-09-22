using System.Net.Sockets;
using System.Text;
using Newtonsoft.Json;
using System.Xml.Serialization;

namespace BrokerUI;

public class PublisherService
{
	private TcpClient client;
	private NetworkStream stream;
	private StreamWriter writer;
	private string host = "127.0.0.1";
	private int port = 5000;

	public async Task ConnectAsync()
	{
		client = new TcpClient();
		await client.ConnectAsync(host, port);
		stream = client.GetStream();
		writer = new StreamWriter(stream, Encoding.UTF8, leaveOpen: true)
		{
			AutoFlush = true
		};
	}

	public async Task SendMessageAsync(Message msg, string format)
	{
		if (writer == null) return;

		string dataToSend = format.ToLower() == "xml"
		    ? "FORMAT:XML|" + SerializeToXml(msg)
		    : "FORMAT:JSON|" + JsonConvert.SerializeObject(msg);

		await writer.WriteLineAsync(dataToSend);
	}

	private string SerializeToXml(object obj)
	{
		var serializer = new XmlSerializer(obj.GetType());
		using var sw = new StringWriter();
		serializer.Serialize(sw, obj);
		return sw.ToString();
	}
}
