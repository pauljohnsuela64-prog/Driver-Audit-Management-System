# Driver Audit Management System

Shared language for BHLI Audit's driver-audit records and individually authenticated staff accounts.

## Language

**Driver audit**:
A record comprising Driver Name, Helper Name, Audit Date, Station, Plate Number, Remarks and Audited By. Record identity and lifecycle information are separate from these seven business fields.
_Avoid_: Employee account, checklist

**Account**:
An individual staff identity with an ADMIN or AUDITOR role. A driver named in an audit does not thereby have an account.
_Avoid_: Driver profile, shared login

**Audited By**:
The historical name of the account holder who created an audit. Later account-name or role changes do not replace this attribution.
_Avoid_: Current editor, current account name

**AUDITOR**:
The staff role permitted to browse active shared audits and edit audits attributed to its own account; it does not identify everyone who can appear in Audited By. An ADMIN can also create an audit.
_Avoid_: Audit owner as a reading restriction

**Audit ownership**:
The relationship between an audit and the individual account that created it. Changing a person's name does not transfer that relationship.
_Avoid_: Name matching

**Archived audit**:
An audit removed from normal active-record browsing while its original attribution and history remain intact.
_Avoid_: Physically deleted audit

**Active account**:
An account currently enabled to authenticate and access permitted functions. Disabling an account does not archive its audits.
_Avoid_: Active audit
