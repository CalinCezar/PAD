[Serializable]
public class Message
{
	public long Id { get; set; }
	public string EventName { get; set; }
	public string Value { get; set; }
	public string Topic { get; set; }
}