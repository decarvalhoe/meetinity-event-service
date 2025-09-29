# 📅 Meetinity Event Service

## ⚠️ **REPOSITORY ARCHIVED - MOVED TO MONOREPO**

**This repository has been archived and is now read-only.**

### 📍 **New Location**
All development has moved to the **Meetinity monorepo**:

**🔗 https://github.com/decarvalhoe/meetinity**

The Event Service is now located at:
```
meetinity/services/event-service/
```

### 🔄 **Migration Complete**
- ✅ **All code** migrated with complete history
- ✅ **Service integrations** with calendar, email, and payment systems
- ✅ **Event management** and registration features
- ✅ **Search and recommendations** functionality
- ✅ **CI/CD pipeline** integrated with unified deployment

### 🛠️ **For Developers**

#### **Clone the monorepo:**
```bash
git clone https://github.com/decarvalhoe/meetinity.git
cd meetinity/services/event-service
```

#### **Development workflow:**
```bash
# Start all services including database
docker compose -f docker-compose.dev.yml up

# Event Service specific development
cd services/event-service
alembic upgrade head  # Run migrations
pytest                # Run tests
```

### 📚 **Documentation**
- **Service Documentation**: `meetinity/services/event-service/README.md`
- **Integration Guide**: `meetinity/services/event-service/docs/integrations.md`
- **Database Migrations**: `meetinity/services/event-service/migrations/`
- **Infrastructure Guide**: `meetinity/docs/service-inventory.md`

### 🔗 **Integration Features**
Now available in the monorepo:
- **Calendar Integration** for event scheduling
- **Email Service** for notifications and invitations
- **Payment Processing** for paid events
- **Social Service** connections and sharing
- **User Service** integration for attendee management
- **Matching Service** integration for networking

### 🏗️ **Architecture Benefits**
The monorepo provides:
- **Unified CI/CD** for all Meetinity services
- **Cross-service integration** testing
- **Consistent event data** management
- **Centralized notification** systems
- **Simplified deployment** and configuration

---

**📅 Archived on:** September 29, 2025  
**🔗 Monorepo:** https://github.com/decarvalhoe/meetinity  
**📧 Questions:** Please open issues in the monorepo

---

## 📋 **Original Service Description**

The Meetinity Event Service powered professional event management with Flask and SQLAlchemy, providing comprehensive event creation, search, and management capabilities with external service integrations.

**Key features now available in the monorepo:**
- Event creation, management, and registration
- CRUD operations with REST API
- Search and recommendation algorithms
- Database migrations with Alembic
- Calendar and scheduling integration
- Payment processing for paid events
- Email notifications and invitations
- Service integrations (calendar, email, payment, social)
