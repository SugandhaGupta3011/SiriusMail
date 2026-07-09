# SiriusMail
Project to create an email marketing service
<img width="1536" height="1024" alt="Architecture" src="https://github.com/user-attachments/assets/c6b70b25-6830-41e0-96a9-de1c4ae2c919" />

## User Flow

Login
↓
Create Audience
↓
Import Contacts
↓
Create Campaign
↓
Preview
↓
Send
↓
View Analytics

## Database

Users
↓
Workspace
↓
Audience
↓
Contacts
↓
Campaign
↓
Email Sends
↓
Email Events

## Sending flow

User clicks Send
↓
API validates campaign
↓
Campaign status → Sending
↓
Messages placed onto SQS
↓
Worker reads queue
↓
SES sends email
↓
Database updated
↓
Analytics recorded


## Next version will add

CSV contact import
Unsubscribe link
Email templates
Campaign scheduling
Send test email
Better validation
Basic bounce handling
Contact status: subscribed/unsubscribed/bounced
