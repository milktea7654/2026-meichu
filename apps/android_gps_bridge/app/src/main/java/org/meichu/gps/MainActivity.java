package org.meichu.gps;

import android.Manifest;
import android.app.Activity;
import android.content.pm.PackageManager;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import org.json.JSONObject;
import java.util.concurrent.TimeUnit;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.WebSocket;
import okhttp3.WebSocketListener;

/** Sensor and transport only. No map, world, event, or AI logic. */
public class MainActivity extends Activity implements LocationListener {
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final OkHttpClient client = new OkHttpClient.Builder().pingInterval(2, TimeUnit.SECONDS).build();
    private LocationManager locations;
    private WebSocket socket;
    private EditText address, token;
    private TextView status;
    private boolean running = false, connected = false;
    private int generation = 0;
    private String endpoint, secret;
    private long retryMs = 1000;

    @Override public void onCreate(Bundle bundle) {
        super.onCreate(bundle);
        locations = (LocationManager) getSystemService(LOCATION_SERVICE);
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setPadding(32, 48, 32, 32);
        TextView title = new TextView(this);
        title.setText(R.string.heading);
        title.setTextSize(22);
        layout.addView(title);
        address = new EditText(this);
        address.setSingleLine(true);
        address.setHint(R.string.address_hint);
        address.setText(getPreferences(MODE_PRIVATE).getString("endpoint", "ws://192.168.43.2:8765/location"));
        layout.addView(address);
        token = new EditText(this);
        token.setSingleLine(true);
        token.setHint(R.string.optional_token);
        token.setInputType(129);
        layout.addView(token);
        Button start = new Button(this);
        start.setText(R.string.start);
        start.setOnClickListener(v -> begin());
        layout.addView(start);
        Button stop = new Button(this);
        stop.setText(R.string.stop);
        stop.setOnClickListener(v -> end());
        layout.addView(stop);
        status = new TextView(this);
        status.setText(R.string.initial_status);
        layout.addView(status);
        setContentView(layout);
    }

    private void begin() {
        if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION}, 1);
            return;
        }
        end();
        endpoint = address.getText().toString().trim();
        secret = token.getText().toString();
        if (!endpoint.startsWith("ws://") || !endpoint.endsWith("/location")) {
            status.setText(R.string.url_help);
            return;
        }
        running = true;
        getPreferences(MODE_PRIVATE).edit().putString("endpoint", endpoint).apply();
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        try {
            locations.requestLocationUpdates(LocationManager.GPS_PROVIDER, 1000, 0, this, Looper.getMainLooper());
            connect(generation);
        } catch (SecurityException | IllegalArgumentException ex) {
            end();
            status.setText(getString(R.string.gps_error, ex.getMessage()));
        }
    }

    private void connect(final int session) {
        if (!running || session != generation) return;
        status.setText(R.string.connecting);
        try {
            Request.Builder request = new Request.Builder().url(endpoint);
            if (!secret.isEmpty()) request.header("Authorization", "Bearer " + secret);
            socket = client.newWebSocket(request.build(), new WebSocketListener() {
                @Override public void onOpen(WebSocket ws, Response response) {
                    handler.post(() -> {
                        if (session != generation || !running) { ws.close(1000, "Stopped"); return; }
                        connected = true;
                        retryMs = 1000;
                        status.setText(R.string.connected);
                    });
                }
                @Override public void onFailure(WebSocket ws, Throwable error, Response response) { retry(session); }
                @Override public void onClosed(WebSocket ws, int code, String reason) { retry(session); }
                @Override public void onClosing(WebSocket ws, int code, String reason) { ws.close(code, reason); }
            });
        } catch (IllegalArgumentException ex) {
            end();
            status.setText(R.string.invalid_url);
        }
    }

    private void retry(int session) {
        handler.post(() -> {
            if (!running || session != generation) return;
            connected = false;
            status.setText(R.string.reconnecting);
            handler.postDelayed(() -> connect(session), retryMs);
            retryMs = Math.min(15000, retryMs * 2);
        });
    }

    @Override public void onLocationChanged(Location fix) {
        if (!running || !connected || socket == null || !fix.hasAccuracy()) return;
        // Never replay a cached location after reconnecting.
        if (android.os.SystemClock.elapsedRealtimeNanos() - fix.getElapsedRealtimeNanos() > 5000000000L) return;
        try {
            JSONObject packet = new JSONObject();
            packet.put("type", "location");
            packet.put("latitude", fix.getLatitude());
            packet.put("longitude", fix.getLongitude());
            packet.put("accuracy_m", fix.getAccuracy());
            packet.put("timestamp_ms", fix.getTime());
            if (fix.hasSpeed()) packet.put("speed_mps", fix.getSpeed());
            if (fix.hasBearing()) packet.put("heading_deg", fix.getBearing());
            if (fix.hasAltitude()) packet.put("altitude_m", fix.getAltitude());
            if (socket.queueSize() > 4096) return;
            socket.send(packet.toString());
            status.setText(getString(R.string.gps_status, fix.getLatitude(), fix.getLongitude(), fix.getAccuracy()));
        } catch (org.json.JSONException ex) {
            status.setText(R.string.invalid_fix);
        }
    }

    @Override public void onProviderDisabled(String provider) { status.setText(R.string.enable_location); }
    @Override public void onProviderEnabled(String provider) { }
    @Override public void onStatusChanged(String provider, int value, Bundle extras) { }
    @Override public void onRequestPermissionsResult(int request, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(request, permissions, results);
        if (request == 1 && checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED) begin();
        else status.setText(R.string.permission_required);
    }
    private void end() {
        running = false;
        connected = false;
        generation++;
        handler.removeCallbacksAndMessages(null);
        if (locations != null) locations.removeUpdates(this);
        if (socket != null) { socket.close(1000, "Stopped"); socket = null; }
        getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        if (status != null) status.setText(R.string.stopped);
    }
    @Override protected void onStop() { end(); super.onStop(); }
    @Override protected void onDestroy() { end(); client.dispatcher().executorService().shutdown(); super.onDestroy(); }
}
