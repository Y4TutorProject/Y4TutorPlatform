# Messaging Service
This service provides messaging features for a students and tutors. It uses Flask and Socket.IO for real time comminication between the client and server.

The key features include: 
* Room based message broadcasting
* Instant message delivery
* File uploads

A user is directed here after a tutoring proposal has been accepted. Authentication is handled by the user service. 

# Environment
SECRET_KEY
A secret key is required to protect the integrity of data in transit.
GENERATE -> python3 -c 'import secrets; print(secrets.token_hex(32))'

SESSION_COOKIE_SECURE
Controls whether session cookies are sent only over HTTPS.
false = HTTP (development)
true  = HTTPS (production)
