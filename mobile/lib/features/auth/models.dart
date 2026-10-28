import '../../core/network/api_failure.dart';
import '../../core/network/json_contract.dart';

class AuthenticatedUser {
  const AuthenticatedUser._(this.id, this.username, this.fullName, this.role);
  final int id;
  final String username;
  final String fullName;
  final String role;
  static AuthenticatedUser fromJson(Object? value) {
    final json = jsonObject(value);
    final role = json['role'];
    if (role != 'ADMIN' && role != 'AUDITOR') throw ApiFailure.unsupportedRole;
    return AuthenticatedUser._(
      positiveInt(json['id']),
      requiredText(json['username'], maxLength: 100),
      requiredText(json['full_name'], maxLength: 200),
      role as String,
    );
  }
}

/// An in-memory credential confined to the transport and session boundary.
class SessionLease {
  const SessionLease._(this.accessToken, this.expiresAt);
  final String accessToken;
  final DateTime expiresAt;
  static SessionLease fromJson(Object? value) {
    final json = jsonObject(value);
    final token = json['access_token'];
    if (token is! String ||
        !validBearer(token) ||
        json['token_type'] != 'bearer') {
      throw ApiFailure.protocol;
    }
    return SessionLease._(token, utcTimestamp(json['expires_at']));
  }

  @override
  String toString() => 'SessionLease(redacted)';
}
