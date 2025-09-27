# Meetinity Event Service

This repository contains the event management service for the Meetinity platform, handling professional events, registrations, and event-related operations.

## Overview

The Event Service is built with **Python Flask** and provides comprehensive event management capabilities for the Meetinity platform. It handles event creation, management, user registrations, and event discovery features.

## Features

- **Event Management**: Complete CRUD operations for professional events
- **Data Validation**: Robust input validation with detailed error messages
- **Event Discovery**: Search and filtering capabilities for event browsing
- **Registration System**: User registration and attendance tracking (planned)
- **Error Handling**: Comprehensive error handling with standardized responses

## Tech Stack

- **Flask**: Lightweight Python web framework
- **Python**: Core business logic and data processing

## Project Status

- **Progress**: 35%
- **Completed Features**: Basic CRUD API, data validation, error handling, health monitoring
- **Pending Features**: Database integration, user registration system, event categories, search functionality

## Current Implementation

The service currently provides:

- **Mock Event Data**: Sample professional events with realistic information
- **Validation Logic**: Input validation for event creation and updates
- **Error Responses**: Standardized error handling with detailed messages
- **Health Monitoring**: Service health check endpoint

## API Endpoints

- `GET /health` - Service health check
- `GET /events` - Retrieve list of events
- `POST /events` - Create a new event
- `GET /events/<event_id>` - Get specific event details

## Event Data Model

Events include the following information:
- **Basic Info**: Title, description, date, location
- **Event Type**: Category/type of professional event
- **Attendance**: Number of registered attendees
- **Metadata**: Creation and update timestamps

## Getting Started

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the service:
   ```bash
   python src/main.py
   ```

The service will start on port 5003 by default.

## Development Roadmap

### Phase 1 (Current)
- Basic CRUD operations with mock data
- Input validation and error handling
- Health monitoring

### Phase 2 (Next)
- Database integration for persistent storage
- User registration and attendance tracking
- Event search and filtering

### Phase 3 (Future)
- Event recommendations based on user interests
- Calendar integration
- Event analytics and reporting

## Architecture

```
src/
├── main.py              # Application entry point with routes
├── models/              # Data models (to be implemented)
├── services/            # Business logic (to be implemented)
└── utils/               # Utility functions (to be implemented)
```

## Validation Rules

Event validation includes:
- **Title**: Required, non-empty string
- **Attendees**: Optional integer >= 0
- **Date**: Valid date format
- **Location**: Optional string

## Testing

```bash
pytest
flake8 src tests
```
