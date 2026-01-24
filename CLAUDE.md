# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Purpose

This is the **translations repository** for ClientXCMS, a SaaS billing and client management platform. It contains i18n JSON translation files that are consumed by the main ClientXCMS application.

## Architecture

### File Structure

- `locales.json` - Registry of supported locales with metadata (locale code, short key, display name, flag URL)
- `translations/*.json` - Translation files, one per language (en.json, fr.json, de.json, es.json, it.json, nl.json, pt.json, zh.json)

### Translation File Format

Each translation file is a flat JSON object with:
- `"language"` key at root level (display name in French)
- Namespaced keys following pattern `lang.fr.<module>` containing nested translation objects

**Modules/Namespaces:**
- `actionslog` - Admin action history
- `admin` - Admin panel UI
- `auth` - Authentication flows
- `billing` - Invoicing and payments
- `client` - Client portal
- `coupon` - Discount codes
- `errors` - Error messages
- `extensions` - Plugin system
- `global` - Shared strings
- `helpdesk` - Support tickets
- `http-statuses` - HTTP error pages
- `install` - Setup wizard
- `maintenance` - Maintenance mode
- `pagination` - Pagination controls
- `passwords` - Password management
- `permissions` - RBAC labels
- `personalization` - Theming/branding
- `provisioning` - Service automation
- `recurring` - Subscription billing
- `store` - Product catalog
- `validation` - Form validation messages
- `webhook` - Webhook configuration

### Locale Registry (locales.json)

Maps full locale codes (e.g., `fr_FR`, `en_GB`) to:
- `key` - Short code used in translation filenames (e.g., `fr`, `en`)
- `name` - Native language name
- `flag` - Flag icon URL from flagsapi.com

## Translation Conventions

- **Reference language:** French (fr.json) is the most complete and serves as reference
- **Placeholders:** Use `{_variable}` syntax (e.g., `{_name}`, `{_count}`, `{_date}`)
- **Key consistency:** All translation files must have identical key structures
- **Encoding:** UTF-8 with 4-space indentation
