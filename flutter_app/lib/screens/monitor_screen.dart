import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../models/localization_result.dart';
import '../models/optitrack_result.dart';
import '../providers/connection_provider.dart';
import '../providers/optitrack_provider.dart';
import '../services/optitrack_service.dart';

class MonitorScreen extends StatefulWidget {
  const MonitorScreen({super.key});

  @override
  State<MonitorScreen> createState() => _MonitorScreenState();
}

class _MonitorScreenState extends State<MonitorScreen> {
  Timer? _timer;
  // Only ever updated with a fully valid (non-error) result, so the display
  // never flickers back to a blank/error screen on a transient hiccup -- we
  // just keep showing the last known good location.
  LocalizationResult? _lastGoodResult;
  String? _statusMessage;
  bool _isPolling = false;
  // Updated from every response that actually reaches us, success or
  // "not enough markers" error alike -- unlike _lastGoodResult, this is
  // meant to reflect what the rig sees *right now*, which is most useful
  // exactly when localization is failing and you're trying to see why.
  int? _markersSeen;
  List<int> _markerIds = const [];
  Map<String, double?> _cameraTimes = const {};
  // Pipeline's own cycle rate, updated from every response like
  // _markersSeen -- most useful exactly when things are going wrong, so it
  // shouldn't only track the last *good* result.
  double? _fps;
  // Guards against overlapping requests: at a 150ms poll interval, a single
  // slow HTTP round trip (network hiccup, server hang) could otherwise let
  // ticks pile up into a growing backlog of concurrent requests.
  bool _requestInFlight = false;

  OptiTrackResult? _optitrackResult;
  String? _optitrackError;
  bool _isSendingToOptiTrack = false;

  static const _pollInterval = Duration(milliseconds: 100);

  void _startPolling() {
    _timer?.cancel();
    setState(() => _isPolling = true);
    _poll();
    _timer = Timer.periodic(_pollInterval, (_) => _poll());
  }

  void _stopPolling() {
    _timer?.cancel();
    _timer = null;
    setState(() => _isPolling = false);
  }

  Future<void> _poll() async {
    if (_requestInFlight) return;
    final conn = context.read<ConnectionProvider>();
    if (!conn.isConnected) {
      if (mounted) setState(() => _statusMessage = 'Not connected to Pi.');
      return;
    }
    _requestInFlight = true;
    try {
      final result = await conn.service.getLocalization();
      if (!mounted) return;
      setState(() {
        if (result == null) {
          _statusMessage = 'No localization data available yet.';
        } else if (result.error != null) {
          _statusMessage = result.error;
          _markersSeen = result.markersDetected;
          _markerIds = result.markerIds;
          _cameraTimes = result.cameraResponseTimes;
          _fps = result.fps;
        } else {
          _statusMessage = null;
          _lastGoodResult = result;
          _markersSeen = result.markersDetected;
          _markerIds = result.markerIds;
          _cameraTimes = result.cameraResponseTimes;
          _fps = result.fps;
        }
      });
    } catch (e) {
      if (mounted) {
        setState(() => _statusMessage = '$e');
      }
    } finally {
      _requestInFlight = false;
    }
  }

  Future<void> _sendToOptiTrack() async {
    final result = _lastGoodResult;
    if (result == null || _isSendingToOptiTrack) return;
    final optitrack = context.read<OptiTrackProvider>();
    setState(() {
      _isSendingToOptiTrack = true;
      _optitrackError = null;
    });
    try {
      // The server retries internally until OptiTrack answers, so this can
      // take a while -- see optitrack_server/server.py.
      final comparison = await optitrack.service.compare(
        x: result.x,
        y: result.y,
        z: result.z,
      );
      if (!mounted) return;
      setState(() => _optitrackResult = comparison);
    } on OptiTrackServiceException catch (e) {
      if (mounted) setState(() => _optitrackError = e.message);
    } catch (e) {
      if (mounted) setState(() => _optitrackError = '$e');
    } finally {
      if (mounted) setState(() => _isSendingToOptiTrack = false);
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final conn = context.watch<ConnectionProvider>();

    return Scaffold(
      appBar: AppBar(
        title: const Text('Live Monitor'),
        backgroundColor: cs.primaryContainer,
        foregroundColor: cs.onPrimaryContainer,
        actions: [
          IconButton(
            icon: Icon(_isPolling ? Icons.pause : Icons.play_arrow),
            tooltip: _isPolling ? 'Pause' : 'Start polling',
            onPressed: conn.isConnected
                ? (_isPolling ? _stopPolling : _startPolling)
                : null,
          ),
        ],
      ),
      body: Column(
        children: [
          _PollingStatusBar(
            isPolling: _isPolling,
            isConnected: conn.isConnected,
            lastUpdate: _lastGoodResult?.timestamp,
            fps: _fps,
          ),
          _MarkersSeenBar(count: _markersSeen, ids: _markerIds),
          _CameraTimingsBar(times: _cameraTimes),
          // Once we have a last-known location, keep it on screen -- a lost
          // connection or a transient "too few markers" reading only shows a
          // thin banner, it never blanks out the display.
          if (_lastGoodResult != null && _statusMessage != null)
            _StaleBanner(message: _statusMessage!),
          Expanded(
            child: _lastGoodResult != null
                ? _LocalizationDisplay(
                    result: _lastGoodResult!,
                    optitrackResult: _optitrackResult,
                    optitrackError: _optitrackError,
                    isSendingToOptiTrack: _isSendingToOptiTrack,
                    onSendToOptiTrack: _sendToOptiTrack,
                  )
                : _statusMessage != null
                    ? _ErrorState(message: _statusMessage!)
                    : _IdleState(
                        isConnected: conn.isConnected,
                        isPolling: _isPolling,
                        onStart: conn.isConnected ? _startPolling : null,
                      ),
          ),
        ],
      ),
    );
  }
}

class _PollingStatusBar extends StatelessWidget {
  final bool isPolling;
  final bool isConnected;
  final DateTime? lastUpdate;
  // Pipeline's own cycle rate (see pipeline/fps_tracker.py) -- how fast the
  // Pi itself is producing new positions, independent of our poll interval.
  final double? fps;

  const _PollingStatusBar({
    required this.isPolling,
    required this.isConnected,
    this.lastUpdate,
    this.fps,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    Color bg;
    String label;
    if (!isConnected) {
      bg = cs.errorContainer;
      label = 'Not connected to Pi';
    } else if (isPolling) {
      bg = cs.secondaryContainer;
      label = 'Polling every 150 ms';
    } else {
      bg = cs.surfaceVariant;
      label = 'Paused';
    }

    return Container(
      width: double.infinity,
      color: bg,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Row(
        children: [
          if (isPolling)
            const SizedBox(
              width: 14,
              height: 14,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          else
            Icon(
              isConnected ? Icons.pause_circle_outline : Icons.wifi_off,
              size: 16,
            ),
          const SizedBox(width: 8),
          Text(label, style: const TextStyle(fontSize: 13)),
          const Spacer(),
          if (fps != null) ...[
            Icon(Icons.speed, size: 14, color: Theme.of(context).colorScheme.onSurfaceVariant),
            const SizedBox(width: 4),
            Text(
              '${fps!.toStringAsFixed(1)} FPS',
              style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600),
            ),
            const SizedBox(width: 12),
          ],
          if (lastUpdate != null)
            Text(
              'Last: ${_fmt(lastUpdate!)}',
              style: const TextStyle(fontSize: 11),
            ),
        ],
      ),
    );
  }

  String _fmt(DateTime dt) {
    final local = dt.toLocal();
    return '${local.hour.toString().padLeft(2, '0')}:'
        '${local.minute.toString().padLeft(2, '0')}:'
        '${local.second.toString().padLeft(2, '0')}';
  }
}

class _MarkersSeenBar extends StatelessWidget {
  final int? count;
  final List<int> ids;

  const _MarkersSeenBar({required this.count, required this.ids});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Container(
      width: double.infinity,
      color: cs.surfaceVariant.withOpacity(0.5),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Icon(Icons.qr_code_scanner, size: 16, color: cs.onSurfaceVariant),
          const SizedBox(width: 8),
          Text(
            count == null ? 'Markers seen: --' : 'Markers seen: $count',
            style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w600,
              color: cs.onSurfaceVariant,
            ),
          ),
          if (ids.isNotEmpty) ...[
            const SizedBox(width: 12),
            Expanded(
              child: Wrap(
                spacing: 6,
                runSpacing: 4,
                children: [
                  for (final id in ids)
                    Chip(
                      label: Text('#$id', style: const TextStyle(fontSize: 11)),
                      visualDensity: VisualDensity.compact,
                      materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      padding: EdgeInsets.zero,
                      backgroundColor: cs.primaryContainer.withOpacity(0.6),
                    ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _CameraTimingsBar extends StatelessWidget {
  final Map<String, double?> times;

  const _CameraTimingsBar({required this.times});

  @override
  Widget build(BuildContext context) {
    if (times.isEmpty) return const SizedBox.shrink();
    final cs = Theme.of(context).colorScheme;
    final names = times.keys.toList()..sort();

    return Container(
      width: double.infinity,
      color: cs.surfaceVariant.withOpacity(0.25),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      child: Wrap(
        spacing: 14,
        runSpacing: 4,
        children: [
          for (final name in names) _CameraTimingLabel(name: name, seconds: times[name]),
        ],
      ),
    );
  }
}

class _CameraTimingLabel extends StatelessWidget {
  final String name;
  // Most recently *completed* round trip for this camera. Null means it
  // hasn't answered yet this cycle -- still catching up, not disconnected
  // (see camera_link.py: a slow camera is skipped, never kicked).
  final double? seconds;

  const _CameraTimingLabel({required this.name, required this.seconds});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final responded = seconds != null;
    final text = responded
        ? '$name ${(seconds! * 1000).toStringAsFixed(0)} ms'
        : '$name waiting…';
    final color = responded ? cs.onSurfaceVariant : cs.error;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(
          responded ? Icons.camera_alt_outlined : Icons.hourglass_empty,
          size: 13,
          color: color,
        ),
        const SizedBox(width: 4),
        Text(text, style: TextStyle(fontSize: 12, color: color)),
      ],
    );
  }
}

class _StaleBanner extends StatelessWidget {
  final String message;
  const _StaleBanner({required this.message});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      color: Colors.amber.withOpacity(0.25),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      child: Row(
        children: [
          const Icon(Icons.warning_amber_rounded, size: 16, color: Colors.amber),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              '$message Showing last known location.',
              style: const TextStyle(fontSize: 12),
            ),
          ),
        ],
      ),
    );
  }
}

class _LocalizationDisplay extends StatelessWidget {
  final LocalizationResult result;
  final OptiTrackResult? optitrackResult;
  final String? optitrackError;
  final bool isSendingToOptiTrack;
  final VoidCallback onSendToOptiTrack;

  const _LocalizationDisplay({
    required this.result,
    required this.optitrackResult,
    required this.optitrackError,
    required this.isSendingToOptiTrack,
    required this.onSendToOptiTrack,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        children: [
          const SizedBox(height: 8),
          Text('Position', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 16),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: [
              _ValueChip(label: 'X', value: result.x, color: cs.primary),
              _ValueChip(label: 'Y', value: result.y, color: cs.secondary),
              _ValueChip(label: 'Z', value: result.z, color: cs.tertiary),
            ],
          ),
          const SizedBox(height: 24),
          const Divider(),
          const SizedBox(height: 16),
          _InfoRow(
            icon: Icons.adjust,
            label: 'Confidence',
            value: '${(result.confidence * 100).toStringAsFixed(1)} %',
          ),
          const SizedBox(height: 12),
          _InfoRow(
            icon: Icons.qr_code_2,
            label: 'Markers detected',
            value: '${result.markersDetected}',
          ),
          const SizedBox(height: 24),
          _ConfidenceBar(confidence: result.confidence),
          const SizedBox(height: 24),
          const Divider(),
          const SizedBox(height: 16),
          _OptiTrackSection(
            optitrackResult: optitrackResult,
            optitrackError: optitrackError,
            isSending: isSendingToOptiTrack,
            onSend: onSendToOptiTrack,
          ),
        ],
      ),
    );
  }
}

class _OptiTrackSection extends StatelessWidget {
  final OptiTrackResult? optitrackResult;
  final String? optitrackError;
  final bool isSending;
  final VoidCallback onSend;

  const _OptiTrackSection({
    required this.optitrackResult,
    required this.optitrackError,
    required this.isSending,
    required this.onSend,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final result = optitrackResult;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Ground Truth (OptiTrack)',
            style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 12),
        SizedBox(
          width: double.infinity,
          child: FilledButton.icon(
            onPressed: isSending ? null : onSend,
            icon: isSending
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.rule),
            label: Text(isSending
                ? 'Waiting for OptiTrack…'
                : 'Send to OptiTrack'),
          ),
        ),
        if (optitrackError != null) ...[
          const SizedBox(height: 12),
          Text(
            optitrackError!,
            style: TextStyle(color: cs.error, fontSize: 13),
          ),
        ],
        if (result != null) ...[
          const SizedBox(height: 16),
          _InfoRow(
            icon: Icons.straighten,
            label: 'Error',
            value: '${(result.errorM * 100).toStringAsFixed(1)} cm',
          ),
          const SizedBox(height: 12),
          _InfoRow(
            icon: Icons.my_location,
            label: 'OptiTrack position',
            value:
                '(${result.groundTruthX.toStringAsFixed(3)}, ${result.groundTruthY.toStringAsFixed(3)}, ${result.groundTruthZ.toStringAsFixed(3)})',
          ),
          if (result.failedAttempts > 0) ...[
            const SizedBox(height: 12),
            _InfoRow(
              icon: Icons.bug_report_outlined,
              label: 'OptiTrack retries needed',
              value: '${result.failedAttempts}',
            ),
          ],
        ],
      ],
    );
  }
}

class _ValueChip extends StatelessWidget {
  final String label;
  final double value;
  final Color color;

  const _ValueChip({
    required this.label,
    required this.value,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Container(
          width: 96,
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 16),
          decoration: BoxDecoration(
            color: color.withOpacity(0.12),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: color.withOpacity(0.4)),
          ),
          child: Column(
            children: [
              Text(
                value.toStringAsFixed(3),
                style: TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.bold,
                  color: color,
                  fontFamily: 'monospace',
                ),
              ),
              const SizedBox(height: 4),
              Text('m', style: TextStyle(color: color, fontSize: 11)),
            ],
          ),
        ),
        const SizedBox(height: 6),
        Text(
          label,
          style: TextStyle(
            fontWeight: FontWeight.bold,
            color: color,
            fontSize: 16,
          ),
        ),
      ],
    );
  }
}

class _InfoRow extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;

  const _InfoRow({
    required this.icon,
    required this.label,
    required this.value,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Row(
      children: [
        Icon(icon, size: 20, color: cs.primary),
        const SizedBox(width: 12),
        Text(label),
        const Spacer(),
        Text(
          value,
          style: const TextStyle(fontWeight: FontWeight.bold),
        ),
      ],
    );
  }
}

class _ConfidenceBar extends StatelessWidget {
  final double confidence;
  const _ConfidenceBar({required this.confidence});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final color = confidence > 0.7
        ? Colors.green
        : confidence > 0.4
            ? Colors.orange
            : cs.error;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Confidence', style: Theme.of(context).textTheme.labelMedium),
        const SizedBox(height: 8),
        ClipRRect(
          borderRadius: BorderRadius.circular(4),
          child: LinearProgressIndicator(
            value: confidence.clamp(0.0, 1.0),
            minHeight: 10,
            backgroundColor: cs.surfaceVariant,
            valueColor: AlwaysStoppedAnimation<Color>(color),
          ),
        ),
      ],
    );
  }
}

class _IdleState extends StatelessWidget {
  final bool isConnected;
  final bool isPolling;
  final VoidCallback? onStart;

  const _IdleState({
    required this.isConnected,
    required this.isPolling,
    required this.onStart,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.gps_not_fixed, size: 72, color: cs.outlineVariant),
          const SizedBox(height: 16),
          Text(
            isConnected ? 'Press play to start monitoring' : 'Connect to Pi first',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          if (onStart != null) ...[
            const SizedBox(height: 24),
            FilledButton.icon(
              onPressed: onStart,
              icon: const Icon(Icons.play_arrow),
              label: const Text('Start Monitoring'),
            ),
          ],
        ],
      ),
    );
  }
}

class _ErrorState extends StatelessWidget {
  final String message;
  const _ErrorState({required this.message});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.error_outline, size: 56, color: cs.error),
            const SizedBox(height: 16),
            Text(
              message,
              textAlign: TextAlign.center,
              style: TextStyle(color: cs.error),
            ),
          ],
        ),
      ),
    );
  }
}
