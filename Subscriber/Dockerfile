# C# Subscriber Dockerfile
FROM mcr.microsoft.com/dotnet/sdk:9.0 AS build

WORKDIR /app

# Copy project files
COPY *.csproj .
RUN dotnet restore

# Copy source code
COPY . .
RUN dotnet publish -c Release -o out

# Runtime image
FROM mcr.microsoft.com/dotnet/runtime:9.0
WORKDIR /app
COPY --from=build /app/out .

# Run the subscriber
ENTRYPOINT ["dotnet", "Subscriber.dll"]