# Meetinity Event Service - Infrastructure Documentation

## Service Overview

The **Meetinity Event Service** manages event creation, discovery, registration, and attendance tracking within the Meetinity professional networking platform. This service handles all event-related operations and integrates with other microservices through Kafka messaging.

## Architecture Position

```mermaid
graph TD
    A[Mobile App :3000] --> B[API Gateway :8080]
    C[Admin Portal :3001] --> B
    B --> D[User Service :8081]
    B --> E[Event Service :8083]
    B --> F[Matching Service :8082]
    
    D --> G[PostgreSQL :5432]
    E --> G
    F --> G
    
    D --> H[Redis :6379]
    E --> I[Kafka :9092]
    D --> I
    F --> I
    
    I --> J[Zookeeper :2181]
```

## Infrastructure Requirements

### System Dependencies
- **Python 3.11+** - Runtime environment
- **PostgreSQL 15** - Primary database
- **Apache Kafka 3.5** - Event streaming
- **Zookeeper 3.9** - Kafka coordination
- **Docker** - Containerization (optional)

### Resource Requirements
- **CPU**: 2 cores minimum, 4 cores recommended
- **Memory**: 2GB minimum, 4GB recommended
- **Storage**: 10GB minimum for logs and temporary files
- **Network**: 1Gbps for inter-service communication

## Database Schema

### Events Table
```sql
CREATE TABLE events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    location VARCHAR(255),
    latitude DECIMAL(10, 8),
    longitude DECIMAL(11, 8),
    start_date TIMESTAMP NOT NULL,
    end_date TIMESTAMP,
    max_attendees INTEGER,
    current_attendees INTEGER DEFAULT 0,
    category VARCHAR(100),
    tags TEXT[],
    image_url TEXT,
    is_virtual BOOLEAN DEFAULT FALSE,
    virtual_link TEXT,
    price DECIMAL(10, 2) DEFAULT 0.00,
    currency VARCHAR(3) DEFAULT 'USD',
    status VARCHAR(20) DEFAULT 'active', -- active, cancelled, completed
    created_by UUID NOT NULL, -- References users(id) from User Service
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_events_start_date ON events(start_date);
CREATE INDEX idx_events_location ON events(location);
CREATE INDEX idx_events_category ON events(category);
CREATE INDEX idx_events_status ON events(status);
CREATE INDEX idx_events_created_by ON events(created_by);
CREATE INDEX idx_events_tags ON events USING GIN(tags);
```

### Event Registrations Table
```sql
CREATE TABLE event_registrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID REFERENCES events(id) ON DELETE CASCADE,
    user_id UUID NOT NULL, -- References users(id) from User Service
    status VARCHAR(20) DEFAULT 'registered', -- registered, cancelled, attended, no_show
    registration_data JSONB, -- Additional registration info
    registered_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(event_id, user_id)
);

-- Indexes
CREATE INDEX idx_registrations_event ON event_registrations(event_id);
CREATE INDEX idx_registrations_user ON event_registrations(user_id);
CREATE INDEX idx_registrations_status ON event_registrations(status);
```

### Event Categories Table
```sql
CREATE TABLE event_categories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    icon VARCHAR(50),
    color VARCHAR(7), -- Hex color code
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Insert default categories
INSERT INTO event_categories (name, description, icon, color) VALUES
('Networking', 'Professional networking events', 'network', '#3B82F6'),
('Workshop', 'Educational workshops and training', 'workshop', '#10B981'),
('Conference', 'Industry conferences and summits', 'conference', '#8B5CF6'),
('Meetup', 'Casual meetups and social events', 'meetup', '#F59E0B'),
('Webinar', 'Online webinars and presentations', 'webinar', '#EF4444'),
('Career', 'Career development and job fairs', 'career', '#6366F1');
```

## Service Configuration

### Environment Variables
```env
# Service Configuration
APP_PORT=8083
LOG_LEVEL=INFO
FLASK_ENV=production

# Database Configuration
DATABASE_URL=postgresql://meetinity:meetinity@localhost:5432/meetinity

# Kafka Configuration
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_EVENT_TOPIC=event.events
KAFKA_CONSUMER_GROUP=event-service

# External Service URLs
USER_SERVICE_URL=http://localhost:8081
API_GATEWAY_URL=http://localhost:8080

# File Upload Configuration
UPLOAD_FOLDER=uploads/events
MAX_CONTENT_LENGTH=16777216  # 16MB
ALLOWED_EXTENSIONS=jpg,jpeg,png,gif

# Pagination Configuration
DEFAULT_PAGE_SIZE=20
MAX_PAGE_SIZE=100

# Cache Configuration
CACHE_TTL=3600  # 1 hour

# CORS Configuration
CORS_ORIGINS=http://localhost:3000,http://localhost:3001,http://localhost:8080
```

### Docker Configuration
```dockerfile
# Multi-stage build
FROM python:3.11-slim as builder
RUN apt-get update && apt-get install -y build-essential gcc
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install -r requirements.txt

FROM python:3.11-slim as runtime
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
RUN groupadd -r meetinity && useradd -r -g meetinity meetinity
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /app
COPY --chown=meetinity:meetinity . .
USER meetinity
EXPOSE 8083
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8083/health || exit 1
CMD ["gunicorn", "--bind", "0.0.0.0:8083", "--workers", "4", "src.main:create_app()"]
```

## Inter-Service Communication

### Kafka Events Published
```python
# Event created
{
    "event_type": "event.created",
    "event_id": "uuid",
    "title": "Tech Networking Meetup",
    "category": "Networking",
    "start_date": "2025-10-15T18:00:00Z",
    "location": "San Francisco, CA",
    "created_by": "user-uuid",
    "timestamp": "2025-09-28T16:30:00Z"
}

# Event updated
{
    "event_type": "event.updated",
    "event_id": "uuid",
    "updated_fields": ["title", "description", "start_date"],
    "timestamp": "2025-09-28T16:30:00Z"
}

# User registered for event
{
    "event_type": "event.registration.created",
    "event_id": "uuid",
    "user_id": "user-uuid",
    "registration_id": "registration-uuid",
    "timestamp": "2025-09-28T16:30:00Z"
}

# Event cancelled
{
    "event_type": "event.cancelled",
    "event_id": "uuid",
    "reason": "Insufficient registrations",
    "affected_users": ["user-uuid-1", "user-uuid-2"],
    "timestamp": "2025-09-28T16:30:00Z"
}
```

### Kafka Events Consumed
```python
# User profile updated (for event recommendations)
{
    "event_type": "user.updated",
    "user_id": "uuid",
    "updated_fields": ["location", "industry", "interests"],
    "location": "San Francisco, CA",
    "industry": "Technology",
    "interests": ["AI", "Blockchain"],
    "timestamp": "2025-09-28T16:30:00Z"
}

# User deleted (cleanup registrations)
{
    "event_type": "user.deleted",
    "user_id": "uuid",
    "timestamp": "2025-09-28T16:30:00Z"
}
```

### API Integration Points

#### User Service Integration
```python
# Validate user exists and is active
GET /users/{user_id}/validate
Response: {"exists": true, "is_active": true, "name": "John Doe"}

# Get user profile for event recommendations
GET /users/{user_id}/profile
Response: {
    "id": "uuid",
    "name": "John Doe",
    "location": "San Francisco, CA",
    "industry": "Technology",
    "interests": ["AI", "Networking"]
}

# Get multiple user profiles (for attendee lists)
POST /users/batch
Body: {"user_ids": ["uuid1", "uuid2", "uuid3"]}
Response: [{"id": "uuid1", "name": "John Doe", ...}, ...]
```

#### Matching Service Integration
```python
# Notify about event attendance for matching
POST /matches/events/attendance
Body: {
    "event_id": "uuid",
    "attendees": ["user-uuid-1", "user-uuid-2"],
    "event_category": "Networking",
    "event_tags": ["tech", "startup"]
}
```

## Deployment Architecture

### Local Development
```bash
# Start dependencies
docker-compose up -d postgres kafka zookeeper

# Start service
python src/main.py
```

### Docker Compose Integration
```yaml
version: "3.9"
services:
  event-service:
    build: ../meetinity-event-service
    ports: ["8083:8083"]
    environment:
      - DATABASE_URL=postgresql://meetinity:meetinity@postgres:5432/meetinity
      - KAFKA_BOOTSTRAP_SERVERS=kafka:9092
      - USER_SERVICE_URL=http://user-service:8081
    depends_on:
      - postgres
      - kafka
      - user-service
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8083/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### Kubernetes Deployment
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: event-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: event-service
  template:
    metadata:
      labels:
        app: event-service
    spec:
      containers:
      - name: event-service
        image: meetinity/event-service:latest
        ports:
        - containerPort: 8083
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: database-secret
              key: url
        - name: KAFKA_BOOTSTRAP_SERVERS
          value: "kafka:9092"
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8083
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8083
          initialDelaySeconds: 5
          periodSeconds: 5
```

## Monitoring and Observability

### Health Check Endpoint
```python
GET /health
Response:
{
    "status": "ok",
    "service": "event-service",
    "version": "1.0.0",
    "dependencies": {
        "database": "up",
        "kafka": "up",
        "user_service": "up"
    },
    "metrics": {
        "total_events": 1250,
        "active_events": 450,
        "total_registrations": 5600,
        "events_today": 12
    }
}
```

### Metrics Collection
```python
# Prometheus metrics
from prometheus_client import Counter, Histogram, Gauge

# Counters
events_created_total = Counter('events_created_total', 'Total events created')
registrations_total = Counter('registrations_total', 'Total event registrations')
api_requests_total = Counter('api_requests_total', 'Total API requests', ['method', 'endpoint'])

# Histograms
request_duration = Histogram('request_duration_seconds', 'Request duration')
event_processing_time = Histogram('event_processing_seconds', 'Event processing time')

# Gauges
active_events = Gauge('active_events', 'Number of active events')
upcoming_events = Gauge('upcoming_events', 'Number of upcoming events')
```

### Logging Configuration
```python
LOGGING_CONFIG = {
    "version": 1,
    "formatters": {
        "json": {
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s"
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json"
        }
    },
    "loggers": {
        "event_service": {
            "level": "INFO",
            "handlers": ["console"]
        },
        "kafka": {
            "level": "WARNING",
            "handlers": ["console"]
        }
    }
}
```

## Security Considerations

### Authentication & Authorization
- **JWT Validation**: All endpoints require valid JWT tokens
- **Role-Based Access**: Admin endpoints require admin role
- **Event Ownership**: Users can only modify their own events
- **Registration Limits**: Prevent spam registrations

### Data Validation
```python
# Event creation validation
{
    "title": {"required": True, "max_length": 255},
    "description": {"max_length": 5000},
    "start_date": {"required": True, "format": "datetime"},
    "end_date": {"format": "datetime", "after": "start_date"},
    "max_attendees": {"type": "integer", "min": 1, "max": 10000},
    "location": {"max_length": 255},
    "category": {"required": True, "choices": ["Networking", "Workshop", ...]},
    "tags": {"type": "array", "max_items": 10}
}
```

### Rate Limiting
```python
RATE_LIMITS = {
    "/events": "100/hour",           # Event browsing
    "/events/create": "10/hour",     # Event creation
    "/events/register": "50/hour",   # Event registration
    "/events/search": "200/hour"     # Event search
}
```

## Performance Optimization

### Database Optimization
```sql
-- Partitioning for large event tables
CREATE TABLE events_2025 PARTITION OF events
FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');

-- Materialized view for event statistics
CREATE MATERIALIZED VIEW event_stats AS
SELECT 
    category,
    COUNT(*) as total_events,
    AVG(current_attendees) as avg_attendees,
    DATE_TRUNC('month', created_at) as month
FROM events 
WHERE status = 'active'
GROUP BY category, DATE_TRUNC('month', created_at);

-- Refresh stats hourly
CREATE OR REPLACE FUNCTION refresh_event_stats()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY event_stats;
END;
$$ LANGUAGE plpgsql;
```

### Caching Strategy
```python
# Redis caching for frequently accessed data
CACHE_KEYS = {
    "event_details": "event:{event_id}",
    "event_attendees": "event:{event_id}:attendees",
    "user_events": "user:{user_id}:events",
    "popular_events": "events:popular:{location}",
    "event_categories": "events:categories"
}

CACHE_TIMEOUTS = {
    "event_details": 1800,      # 30 minutes
    "event_attendees": 300,     # 5 minutes
    "user_events": 600,         # 10 minutes
    "popular_events": 3600,     # 1 hour
    "event_categories": 86400   # 24 hours
}
```

## Disaster Recovery

### Backup Strategy
```bash
# Database backup
pg_dump -h localhost -U meetinity meetinity > backup_$(date +%Y%m%d_%H%M%S).sql

# Automated backup script
#!/bin/bash
BACKUP_DIR="/backups/event-service"
DATE=$(date +%Y%m%d_%H%M%S)
pg_dump -h $DB_HOST -U $DB_USER $DB_NAME | gzip > $BACKUP_DIR/events_$DATE.sql.gz

# Keep only last 30 days of backups
find $BACKUP_DIR -name "events_*.sql.gz" -mtime +30 -delete
```

### Recovery Procedures
```bash
# Restore from backup
gunzip -c backup_20250928_163000.sql.gz | psql -h localhost -U meetinity meetinity

# Kafka topic recreation
kafka-topics.sh --create --bootstrap-server localhost:9092 \
    --topic event.events --partitions 3 --replication-factor 1
```

## Troubleshooting Guide

### Common Issues

#### Database Connection Issues
```bash
# Test database connectivity
psql -h localhost -U meetinity -d meetinity -c "SELECT COUNT(*) FROM events;"

# Check database locks
SELECT * FROM pg_locks WHERE NOT granted;

# Monitor database performance
SELECT query, calls, total_time, mean_time 
FROM pg_stat_statements 
ORDER BY total_time DESC LIMIT 10;
```

#### Kafka Issues
```bash
# Check Kafka connectivity
kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic event.events --from-beginning

# List consumer groups
kafka-consumer-groups.sh --bootstrap-server localhost:9092 --list

# Check consumer lag
kafka-consumer-groups.sh --bootstrap-server localhost:9092 --group event-service --describe
```

#### Service Integration Issues
```bash
# Test User Service connectivity
curl -H "Authorization: Bearer $JWT_TOKEN" http://localhost:8081/users/validate

# Check API Gateway routing
curl -H "Authorization: Bearer $JWT_TOKEN" http://localhost:8080/api/events/health
```

## Related Documentation

- **API Gateway**: [meetinity-api-gateway](https://github.com/decarvalhoe/meetinity-api-gateway)
- **User Service**: [meetinity-user-service](https://github.com/decarvalhoe/meetinity-user-service)
- **Matching Service**: [meetinity-matching-service](https://github.com/decarvalhoe/meetinity-matching-service)
- **Mobile App**: [meetinity-mobile-app](https://github.com/decarvalhoe/meetinity-mobile-app)
- **Admin Portal**: [meetinity-admin-portal](https://github.com/decarvalhoe/meetinity-admin-portal)
- **Main Repository**: [meetinity](https://github.com/decarvalhoe/meetinity)

---

**Status**: 35% Complete - REST API with validation  
**Last Updated**: September 2025  
**Maintainer**: decarvalhoe
