import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/connection_provider.dart';
import '../providers/markers_provider.dart';

class CalibrationScreen extends StatefulWidget {
  const CalibrationScreen({super.key});

  @override
  State<CalibrationScreen> createState() => _CalibrationScreenState();
}

class _CalibrationScreenState extends State<CalibrationScreen> {
  bool _isSending = false;
  bool _isFetching = false;
  String? _lastMessage;
  bool _lastSuccess = false;

  Future<void> _sendToPi() async {
    final conn = context.read<ConnectionProvider>();
    final markers = context.read<MarkersProvider>().markers;
    setState(() {
      _isSending = true;
      _lastMessage = null;
    });
    try {
      await conn.service.sendCalibration(markers.toList());
      setState(() {
        _lastSuccess = true;
        _lastMessage =
            'Sent ${markers.length} marker${markers.length == 1 ? '' : 's'} to Pi successfully.';
      });
    } catch (e) {
      setState(() {
        _lastSuccess = false;
        _lastMessage = 'Error: $e';
      });
    } finally {
      setState(() => _isSending = false);
    }
  }

  Future<void> _fetchFromPi() async {
    final conn = context.read<ConnectionProvider>();
    final markersProvider = context.read<MarkersProvider>();
    setState(() {
      _isFetching = true;
      _lastMessage = null;
    });
    try {
      final piMarkers = await conn.service.getMarkers();
      markersProvider.replaceAll(piMarkers);
      setState(() {
        _lastSuccess = true;
        _lastMessage =
            'Loaded ${piMarkers.length} marker${piMarkers.length == 1 ? '' : 's'} from Pi.';
      });
    } catch (e) {
      setState(() {
        _lastSuccess = false;
        _lastMessage = 'Error: $e';
      });
    } finally {
      setState(() => _isFetching = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final conn = context.watch<ConnectionProvider>();
    final markersProvider = context.watch<MarkersProvider>();
    final markers = markersProvider.markers;
    final canSend = conn.isConnected && markers.isNotEmpty && !_isSending;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Calibration'),
        backgroundColor: cs.primaryContainer,
        foregroundColor: cs.onPrimaryContainer,
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _ConnectionStatusCard(conn: conn),
          const SizedBox(height: 16),
          _SummaryCard(markerCount: markers.length),
          if (_lastMessage != null) ...[
            const SizedBox(height: 16),
            _StatusBanner(message: _lastMessage!, success: _lastSuccess),
          ],
          const SizedBox(height: 24),
          FilledButton.icon(
            onPressed: canSend ? _sendToPi : null,
            icon: _isSending
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.upload),
            label: const Text('Send Calibration to Pi'),
          ),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: (conn.isConnected && !_isFetching) ? _fetchFromPi : null,
            icon: _isFetching
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.download_outlined),
            label: const Text('Fetch Markers from Pi'),
          ),
          const SizedBox(height: 32),
          if (markers.isNotEmpty) ...[
            Text(
              'Markers to send',
              style: Theme.of(context).textTheme.titleSmall,
            ),
            const SizedBox(height: 8),
            ...markers.map(
              (m) => Card(
                margin: const EdgeInsets.symmetric(vertical: 4),
                child: ListTile(
                  leading: CircleAvatar(
                    backgroundColor: cs.secondaryContainer,
                    child: Text(
                      '#${m.markerId}',
                      style: TextStyle(
                        color: cs.onSecondaryContainer,
                        fontSize: 11,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                  title: Text('Marker ${m.markerId}'),
                  subtitle: Text(
                    'X: ${m.x.toStringAsFixed(3)}  '
                    'Y: ${m.y.toStringAsFixed(3)}  '
                    'Z: ${m.z.toStringAsFixed(3)}',
                    style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
                  ),
                ),
              ),
            ),
          ] else
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 32),
              child: Text(
                'No markers to send.\nAdd markers in the Markers tab first.',
                textAlign: TextAlign.center,
                style: TextStyle(color: cs.outline),
              ),
            ),
        ],
      ),
    );
  }
}

class _ConnectionStatusCard extends StatelessWidget {
  final ConnectionProvider conn;
  const _ConnectionStatusCard({required this.conn});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final online = conn.isConnected;
    return Card(
      color: online ? cs.secondaryContainer : cs.errorContainer,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Icon(
              online ? Icons.wifi : Icons.wifi_off,
              color: online ? cs.onSecondaryContainer : cs.onErrorContainer,
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    online ? 'Connected to Pi' : 'Not Connected',
                    style: TextStyle(
                      fontWeight: FontWeight.bold,
                      color: online
                          ? cs.onSecondaryContainer
                          : cs.onErrorContainer,
                    ),
                  ),
                  Text(
                    '${conn.host}:${conn.port}',
                    style: TextStyle(
                      fontSize: 12,
                      color: online
                          ? cs.onSecondaryContainer
                          : cs.onErrorContainer,
                    ),
                  ),
                  if (online && conn.status.version != null)
                    Text(
                      'v${conn.status.version}  ·  '
                      '${conn.status.connectedCameras} camera(s)  ·  '
                      '${conn.status.markersLoaded} markers on Pi',
                      style: TextStyle(
                        fontSize: 11,
                        color: online
                            ? cs.onSecondaryContainer
                            : cs.onErrorContainer,
                      ),
                    ),
                ],
              ),
            ),
            if (!online)
              TextButton(
                onPressed: conn.checkConnection,
                child: const Text('Retry'),
              ),
          ],
        ),
      ),
    );
  }
}

class _SummaryCard extends StatelessWidget {
  final int markerCount;
  const _SummaryCard({required this.markerCount});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Icon(Icons.qr_code_2, color: cs.primary),
            const SizedBox(width: 12),
            Text(
              '$markerCount marker${markerCount == 1 ? '' : 's'} configured locally',
              style: const TextStyle(fontWeight: FontWeight.w500),
            ),
          ],
        ),
      ),
    );
  }
}

class _StatusBanner extends StatelessWidget {
  final String message;
  final bool success;
  const _StatusBanner({required this.message, required this.success});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: success ? cs.secondaryContainer : cs.errorContainer,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          Icon(
            success ? Icons.check_circle_outline : Icons.error_outline,
            color: success ? cs.onSecondaryContainer : cs.onErrorContainer,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              message,
              style: TextStyle(
                color:
                    success ? cs.onSecondaryContainer : cs.onErrorContainer,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
