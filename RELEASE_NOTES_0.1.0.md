# Release Notes - 0.1.0

Release date: 2026-05-26  
Release type: First development release (pre-production)

## Overview
Version 0.1.0 is the first development release of Compliance Import Service. It establishes the baseline product capabilities for importing inspection and follow-up payloads, validating them against schemas, enriching records, and storing canonical documents in Alfresco.

This release is intended for initial adoption, validation, and integration readiness. It has not been deployed to any production environment.

## What is included in 0.1.0
- API support for both inspection import and follow-up import workflows.
- Canonical payload validation for checklist, finding, follow-up report, and follow-up source finding structures.
- Data transformation and enrichment logic to align incoming payloads with canonical models.
- Deterministic identifier generation utilities and updated identifier conventions.
- Follow-up report handling improvements, including filename return behavior and CAP ID consistency checks.
- Expanded automated test coverage for API flows, transformer behavior, models, and ID utilities.
- Docker-based local execution support and sample payloads for dry-run validation.
- Project governance and contributor documentation.

## Audience-focused summary
### For users and integrators
- You can submit inspection and follow-up ZIP payloads through API endpoints and receive structured import feedback.
- Payload contracts are now explicitly enforced through schema validation.
- Example payloads are available to support onboarding and integration testing.

### For developers
- Core ingestion modules and schemas have been aligned around explicit, canonical contracts.
- Identifier generation has been refactored to deterministic utility-based behavior.
- Follow-up processing paths now include stronger consistency behavior and broader test coverage.

### For stakeholders
- This release marks functional baseline readiness for end-to-end ingestion in non-production environments.
- It provides a stable foundation for pilot validation, integration hardening, and production-readiness planning.

## Installation and upgrade
For setup, installation, and local execution instructions, use the repository README only:
- See README.md for environment setup and run instructions.
- See README.md for payload structure examples and endpoint usage.

No additional install or upgrade instructions are provided in this release note.

## Deployment status
- Production deployment: Not deployed.
- Environment status: Development/non-production only.

## Notes
- As the first development release, this version is intended to establish the initial baseline and shared expectations for subsequent incremental releases.
