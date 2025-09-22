using System.Net.Sockets;
using System.Text;

namespace BrokerUI;

public class SubscriberService
{
	private TcpClient client;
	private NetworkStream stream;
	private StreamReader reader;
	private string host = "127.0.0.1";
	private int port = 5000;

	public event Action<string> OnMessageReceived;

	public async Task ConnectAndSubscribeAsync(string topic)
	{
		client = new TcpClient();
		await client.ConnectAsync(host, port);
		stream = client.GetStream();
		reader = new StreamReader(stream);

		// trimite SUBSCRIBE
		var subscribeMsg = "SUBSCRIBE:" + topic;
		var writer = new StreamWriter(stream, Encoding.UTF8, leaveOpen: true)
		{
			AutoFlush = true
		};
		await writer.WriteLineAsync(subscribeMsg);

		_ = Task.Run(ReadLoopAsync);
	}

	private async Task ReadLoopAsync()
	{
		while (true)
		{
			try
			{
				var line = await reader.ReadLineAsync();
				if (line == null) break;

				OnMessageReceived?.Invoke(line);
			}
			catch
			{
				break;
			}
		}
	}
}
