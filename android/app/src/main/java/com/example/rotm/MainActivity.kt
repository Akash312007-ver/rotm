package com.example.rotm

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.*
import com.example.rotm.ui.AuthScreen
import com.example.rotm.ui.WalletScreen
import com.example.rotm.ui.theme.ROTMTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            ROTMTheme {
                var unlocked by remember { mutableStateOf(false) }
                val mesh = remember { MeshManager(applicationContext) }

                if (unlocked) {
                    WalletScreen(mesh = mesh)
                } else {
                    AuthScreen(context = applicationContext) {
                        unlocked = true
                    }
                }
            }
        }
    }
}
