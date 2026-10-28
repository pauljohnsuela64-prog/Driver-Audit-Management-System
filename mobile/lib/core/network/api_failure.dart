/// A failure safe to render or log: never contains server text or credentials.
class ApiFailure implements Exception {
  const ApiFailure._(this.code, this.message, {this.status, this.retryAfter});
  final int? status;
  final String code;
  final String message;
  final Duration? retryAfter;
  static const invalidOrigin = ApiFailure._(
    'invalid_origin',
    'Enter an HTTPS server origin with no path, credentials, query or fragment.',
  );
  static const invalidInput = ApiFailure._(
    'invalid_input',
    'Check the entered values and try again.',
  );
  static const protocol = ApiFailure._(
    'protocol',
    'The server returned an unsupported response.',
  );
  static const unsupportedRole = ApiFailure._(
    'unsupported_role',
    'This account cannot access this application.',
  );
  static const network = ApiFailure._(
    'network',
    'Could not connect securely. Check the connection and try again.',
  );
  static const timeout = ApiFailure._(
    'timeout',
    'The request timed out. Try again.',
  );
  static const canceled = ApiFailure._('canceled', 'The request was canceled.');
  static const busy = ApiFailure._(
    'busy',
    'Wait for the current operation to finish.',
  );

  static ApiFailure fromStatus(int status, {Duration? retryAfter}) =>
      switch (status) {
        401 => const ApiFailure._(
          'unauthorized',
          'Your session has ended. Sign in again.',
          status: 401,
        ),
        403 => const ApiFailure._(
          'forbidden',
          'You do not have permission to view this information.',
          status: 403,
        ),
        404 => const ApiFailure._(
          'not_found',
          'This audit is no longer available.',
          status: 404,
        ),
        422 => const ApiFailure._(
          'invalid_input',
          'Check the entered values and try again.',
          status: 422,
        ),
        429 => ApiFailure._(
          'rate_limited',
          'Too many attempts. Wait before trying again.',
          status: 429,
          retryAfter: retryAfter ?? const Duration(seconds: 30),
        ),
        >= 500 => ApiFailure._(
          'service',
          'The service is unavailable. Try again later.',
          status: status,
        ),
        _ => ApiFailure._(
          'protocol',
          'The server returned an unsupported response.',
          status: status,
        ),
      };
  @override
  String toString() => 'ApiFailure($code): $message';
}
