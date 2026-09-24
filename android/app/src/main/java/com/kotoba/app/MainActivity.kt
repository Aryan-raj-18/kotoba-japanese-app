package com.kotoba.app

import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.res.Configuration
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.net.HttpURLConnection
import java.net.URL

/**
 * Hosts the whole app as a single full-screen WebView pointed at a
 * Flask server that this same process starts locally via Chaquopy
 * (Python-for-Android). Nothing here talks to the network - the
 * "server" is just Python code running inside this app, listening on
 * the loopback address so the WebView can load it like any other page.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private val serverUrl = "http://127.0.0.1:5000/"
    private val handler = Handler(Looper.getMainLooper())
    private var startupAttempts = 0
    private val maxStartupAttempts = 80 // ~20s at 250ms apart; Flask's first import can be slow on first launch

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(this))
        }

        webView = findViewById(R.id.webview)
        webView.settings.javaScriptEnabled = true
        webView.settings.domStorageEnabled = true

        // The page synthesises its own sound effects with the Web Audio
        // API. Android blocks audio until a user gesture by default,
        // which would swallow the first chime of every session.
        webView.settings.mediaPlaybackRequiresUserGesture = false

        // Match the WebView's own backdrop to the system light/dark
        // setting so there's no white flash before the page paints.
        webView.setBackgroundColor(if (isSystemDark()) 0xFF13161A.toInt() else 0xFFEFE7D6.toInt())

        webView.webViewClient = KotobaWebViewClient()

        startFlaskServer()
        pollUntilServerReady()
    }

    private fun isSystemDark(): Boolean {
        val mode = resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK
        return mode == Configuration.UI_MODE_NIGHT_YES
    }

    /**
     * Everything the app itself serves stays in the WebView. Anything
     * else - in practice the Feedback page's mailto: link - is handed to
     * whichever app on the phone handles it, because a WebView can't
     * open a mail composer and would just show an error page.
     */
    private inner class KotobaWebViewClient : WebViewClient() {

        override fun shouldOverrideUrlLoading(
            view: WebView?,
            request: WebResourceRequest?
        ): Boolean {
            val url = request?.url ?: return false
            return handleExternal(url)
        }

        @Deprecated("Needed for API < 24, which minSdk still allows")
        override fun shouldOverrideUrlLoading(view: WebView?, url: String?): Boolean {
            if (url == null) return false
            return handleExternal(Uri.parse(url))
        }

        private fun handleExternal(uri: Uri): Boolean {
            val scheme = uri.scheme?.lowercase() ?: return false
            if (scheme == "http" || scheme == "https") {
                // Local Flask pages load in place; a genuinely remote URL
                // has no business opening inside the app shell.
                return if (uri.host == "127.0.0.1" || uri.host == "localhost") {
                    false
                } else {
                    launch(Intent(Intent.ACTION_VIEW, uri))
                }
            }
            return launch(Intent(Intent.ACTION_VIEW, uri))
        }

        private fun launch(intent: Intent): Boolean {
            return try {
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                startActivity(intent)
                true
            } catch (e: ActivityNotFoundException) {
                Toast.makeText(
                    this@MainActivity,
                    "No app on this phone can open that.",
                    Toast.LENGTH_SHORT
                ).show()
                true
            }
        }
    }

    private fun startFlaskServer() {
        // Flask's app.run() blocks the calling thread forever, so it
        // must never run on the UI thread - this app has exactly one
        // background thread whose only job is to keep it alive.
        Thread {
            val py = Python.getInstance()
            val module = py.getModule("kotoba_app.app")
            module.callAttr("run_server")
        }.start()
    }

    private fun pollUntilServerReady() {
        Thread {
            val up = isServerRespondingNow()
            handler.post {
                if (up) {
                    webView.loadUrl(serverUrl)
                } else if (startupAttempts < maxStartupAttempts) {
                    startupAttempts++
                    handler.postDelayed({ pollUntilServerReady() }, 250)
                } else {
                    // Something's genuinely wrong (not just "still starting up") -
                    // show whatever Flask/Chaquopy last had to say rather than a
                    // silent blank screen.
                    webView.loadUrl(serverUrl)
                }
            }
        }.start()
    }

    private fun isServerRespondingNow(): Boolean {
        return try {
            val conn = URL(serverUrl).openConnection() as HttpURLConnection
            conn.connectTimeout = 200
            conn.readTimeout = 200
            conn.requestMethod = "GET"
            val ok = conn.responseCode == 200
            conn.disconnect()
            ok
        } catch (e: Exception) {
            false
        }
    }

    override fun onBackPressed() {
        if (::webView.isInitialized && webView.canGoBack()) {
            webView.goBack()
        } else {
            super.onBackPressed()
        }
    }
}
