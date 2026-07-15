import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../models/localization_result.dart';
import '../providers/connection_provider.dart';

class MonitorScreen extends StatefulWidget {
  const MonitorScreen({super.key});

  @override
  State<MonitorScreen> createState() => _MonitorScreenState();
}

class _MonitorScreenState extends State<MonitorScreen> {
  Timer? _timer;
  LocalizationResult? _result;
  String? _error;
  bool _isPolling = false;

  static const _pollInterval = Duration(seconds: 1);

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
    final conn = context.read<ConnectionProvider>();
    if (!conn.isConnected) {
      setState(() => _error = 'Not connected to Pi.');
      return;
    }
    try {
      final result = await conn.service.getLocalization();
      if (mounted) {
        setState(() {
          _result = result;
          _error = result == null ? 'No localization data available yet.' : result.error;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() => _error = '$e');
      }
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
            lastUpdate: _result?.timestamp,
          ),
          Expanded(
            child: _error != null
                ? _ErrorState(message: _error!)
                : _result == null
                    ? _IdleState(
                        isConnected: conn.isConnected,
                        isPolling: _isPolling,
                        onStart: conn.isConnected ? _startPolling : null,
                      )
                    : _LocalizationDisplay(result: _result!),
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

  const _PollingStatusBar({
    required this.isPolling,
    required this.isConnected,
    this.lastUpdate,
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
      label = 'Polling every 1 s';
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
          if (lastUpdate != null) ...[
            const Spacer(),
            Text(
              'Last: ${_fmt(lastUpdate!)}',
              style: const TextStyle(fontSize: 11),
            ),
          ],
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

class _LocalizationDisplay extends StatelessWidget {
  final LocalizationResult result;
  const _LocalizationDisplay({required this.result});

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
          if (result.yaw != null) ...[
            const SizedBox(height: 12),
            _InfoRow(
              icon: Icons.rotate_right,
              label: 'Yaw',
              value: '${result.yaw!.toStringAsFixed(2)} °',
            ),
          ],
          const SizedBox(height: 24),
          _ConfidenceBar(confidence: result.confidence),
        ],
      ),
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
