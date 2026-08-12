package com.example.rotm.ui

import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Fingerprint
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.rotm.WalletStore

private val GradientBg = Brush.verticalGradient(
    colors = listOf(Color(0xFF0F0C29), Color(0xFF302B63), Color(0xFF24243E))
)
private val AccentPurple = Color(0xFF7C4DFF)

/**
 * PIN-based lock screen. Handles both first-time PIN setup and unlock on return visits.
 */
@Composable
fun AuthScreen(context: android.content.Context, onUnlocked: () -> Unit) {
    val isSettingUp = remember { !WalletStore.hasPin(context) }
    var pin by remember { mutableStateOf("") }
    var confirmPin by remember { mutableStateOf("") }
    var stage by remember { mutableStateOf(if (isSettingUp) 0 else 1) } // 0=set,1=confirm/unlock
    var error by remember { mutableStateOf<String?>(null) }

    val shake = remember { Animatable(0f) }

    Box(
        modifier = Modifier.fillMaxSize().background(GradientBg),
        contentAlignment = Alignment.Center
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Icon(
                Icons.Default.Fingerprint,
                contentDescription = null,
                tint = AccentPurple,
                modifier = Modifier.size(56.dp)
            )
            Spacer(Modifier.height(16.dp))
            Text(
                if (isSettingUp) {
                    if (stage == 0) "Create a PIN" else "Confirm your PIN"
                } else "Enter PIN",
                color = Color.White,
                fontSize = 22.sp,
                fontWeight = FontWeight.Bold
            )
            Spacer(Modifier.height(8.dp))
            Text(
                "ROTM Wallet",
                color = Color.White.copy(alpha = 0.5f),
                fontSize = 13.sp
            )

            Spacer(Modifier.height(32.dp))

            val currentValue = if (isSettingUp && stage == 1) confirmPin else pin

            Row(
                horizontalArrangement = Arrangement.spacedBy(14.dp),
                modifier = Modifier.offset(x = shake.value.dp)
            ) {
                repeat(4) { i ->
                    Box(
                        modifier = Modifier
                            .size(16.dp)
                            .clip(CircleShape)
                            .background(
                                if (i < currentValue.length) AccentPurple else Color.White.copy(alpha = 0.15f)
                            )
                    )
                }
            }

            error?.let {
                Spacer(Modifier.height(12.dp))
                Text(it, color = Color(0xFFFF5252), fontSize = 13.sp)
            }

            Spacer(Modifier.height(40.dp))

            NumberPad { digit ->
                if (digit == "del") {
                    if (isSettingUp && stage == 1) {
                        if (confirmPin.isNotEmpty()) confirmPin = confirmPin.dropLast(1)
                    } else {
                        if (pin.isNotEmpty()) pin = pin.dropLast(1)
                    }
                    return@NumberPad
                }

                error = null

                if (isSettingUp) {
                    if (stage == 0) {
                        if (pin.length < 4) pin += digit
                        if (pin.length == 4) stage = 1
                    } else {
                        if (confirmPin.length < 4) confirmPin += digit
                        if (confirmPin.length == 4) {
                            if (confirmPin == pin) {
                                WalletStore.setPin(context, pin)
                                onUnlocked()
                            } else {
                                error = "PINs don't match, try again"
                                pin = ""
                                confirmPin = ""
                                stage = 0
                            }
                        }
                    }
                } else {
                    if (pin.length < 4) pin += digit
                    if (pin.length == 4) {
                        if (WalletStore.verifyPin(context, pin)) {
                            onUnlocked()
                        } else {
                            error = "Incorrect PIN"
                            pin = ""
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun NumberPad(onDigit: (String) -> Unit) {
    val rows = listOf(
        listOf("1", "2", "3"),
        listOf("4", "5", "6"),
        listOf("7", "8", "9"),
        listOf("", "0", "del")
    )

    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        rows.forEach { row ->
            Row(horizontalArrangement = Arrangement.spacedBy(24.dp)) {
                row.forEach { key ->
                    if (key.isEmpty()) {
                        Spacer(Modifier.size(64.dp))
                    } else {
                        Surface(
                            onClick = { onDigit(key) },
                            shape = CircleShape,
                            color = Color.White.copy(alpha = 0.06f),
                            modifier = Modifier.size(64.dp)
                        ) {
                            Box(contentAlignment = Alignment.Center) {
                                Text(
                                    if (key == "del") "⌫" else key,
                                    color = Color.White,
                                    fontSize = 22.sp,
                                    fontWeight = FontWeight.Medium
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}
