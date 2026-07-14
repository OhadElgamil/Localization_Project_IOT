import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../providers/connection_provider.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late final TextEditingController _hostCtrl;
  late final TextEditingController _portCtrl;
  final _formKey = GlobalKey<FormState>();

  @override
  void initState() {
    super.initState();
    final conn = context.read<ConnectionProvider>();
    _hostCtrl = TextEditingController(text: conn.host);
    _portCtrl = TextEditingController(text: '${conn.port}');
  }

  @override
  void dispose() {
    _hostCtrl.dispose();
    _portCtrl.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    final host = _hostCtrl.text.trim();
    final port = int.parse(_portCtrl.text.trim());
    await context.read<ConnectionProvider>().updateConnection(host, port);
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Connection settings saved.')),
      );
    }
  }

  Future<void> _testConnection() async {
    final conn = context.read<ConnectionProvider>();
    final ok = await conn.checkConnection();
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(ok ? 'Connected to Pi!' : 'Could not reach Pi.'),
          backgroundColor: ok ? Colors.green : Theme.of(context).colorScheme.error,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final conn = context.watch<ConnectionProvider>();

    return Scaffold(
      appBar: AppBar(
        title: const Text('Settings'),
        backgroundColor: cs.primaryContainer,
        foregroundColor: cs.onPrimaryContainer,
      ),
      body: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          Text('Raspberry Pi Connection',
              style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 16),
          Form(
            key: _formKey,
            child: Column(
              children: [
                TextFormField(
                  controller: _hostCtrl,
                  decoration: const InputDecoration(
                    labelText: 'Pi IP Address',
                    hintText: '192.168.1.100',
                    prefixIcon: Icon(Icons.router_outlined),
                    border: OutlineInputBorder(),
                  ),
                  keyboardType: TextInputType.url,
                  validator: (v) {
                    if (v == null || v.trim().isEmpty) return 'Required';
                    return null;
                  },
                ),
                const SizedBox(height: 16),
                TextFormField(
                  controller: _portCtrl,
                  decoration: const InputDecoration(
                    labelText: 'Port',
                    hintText: '5001',
                    prefixIcon: Icon(Icons.lan_outlined),
                    border: OutlineInputBorder(),
                  ),
                  keyboardType: TextInputType.number,
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                  validator: (v) {
                    if (v == null || v.trim().isEmpty) return 'Required';
                    final n = int.tryParse(v.trim());
                    if (n == null || n < 1 || n > 65535) {
                      return 'Enter a valid port (1–65535)';
                    }
                    return null;
                  },
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: conn.isChecking ? null : _testConnection,
                  icon: conn.isChecking
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.wifi_find_outlined),
                  label: const Text('Test'),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: FilledButton.icon(
                  onPressed: _save,
                  icon: const Icon(Icons.save),
                  label: const Text('Save'),
                ),
              ),
            ],
          ),
          const SizedBox(height: 32),
          const Divider(),
          const SizedBox(height: 16),
          Text('Pi Status', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 12),
          _StatusCard(conn: conn),
          const SizedBox(height: 32),
          const Divider(),
          const SizedBox(height: 16),
          Text('API Endpoints', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          _ApiDocsCard(baseUrl: conn.baseUrl),
        ],
      ),
    );
  }
}

class _StatusCard extends StatelessWidget {
  final ConnectionProvider conn;
  const _StatusCard({required this.conn});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final online = conn.isConnected;
    return Card(
      color: online ? cs.secondaryContainer : cs.surfaceVariant,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            _Row(
              label: 'Status',
              value: online ? 'Online' : 'Offline',
              icon: online ? Icons.check_circle : Icons.cancel,
              color: online ? Colors.green : cs.outline,
            ),
            if (online) ...[
              const SizedBox(height: 8),
              _Row(
                label: 'Cameras',
                value: '${conn.status.connectedCameras}',
                icon: Icons.camera_alt_outlined,
              ),
              const SizedBox(height: 8),
              _Row(
                label: 'Markers on Pi',
                value: '${conn.status.markersLoaded}',
                icon: Icons.qr_code_2_outlined,
              ),
              if (conn.status.version != null) ...[
                const SizedBox(height: 8),
                _Row(
                  label: 'Server version',
                  value: conn.status.version!,
                  icon: Icons.info_outline,
                ),
              ],
            ],
          ],
        ),
      ),
    );
  }
}

class _Row extends StatelessWidget {
  final String label;
  final String value;
  final IconData icon;
  final Color? color;

  const _Row({
    required this.label,
    required this.value,
    required this.icon,
    this.color,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Row(
      children: [
        Icon(icon, size: 18, color: color ?? cs.primary),
        const SizedBox(width: 8),
        Text(label),
        const Spacer(),
        Text(value, style: const TextStyle(fontWeight: FontWeight.bold)),
      ],
    );
  }
}

class _ApiDocsCard extends StatelessWidget {
  final String baseUrl;
  const _ApiDocsCard({required this.baseUrl});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'The app communicates with these endpoints on the Pi:',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 12),
            ..._endpoints(baseUrl).map(
              (e) => Padding(
                padding: const EdgeInsets.symmetric(vertical: 3),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      e.$1,
                      style: const TextStyle(
                        fontFamily: 'monospace',
                        fontSize: 11,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        e.$2,
                        style: const TextStyle(fontSize: 11),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  List<(String, String)> _endpoints(String base) => [
        ('GET ', '$base/api/health'),
        ('GET ', '$base/api/markers'),
        ('POST', '$base/api/markers'),
        ('DEL ', '$base/api/markers'),
        ('GET ', '$base/api/localization'),
      ];
}
