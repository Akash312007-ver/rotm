package com.example.rotm.ui

import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.slideInVertically
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AccountCircle
import androidx.compose.material.icons.filled.Bluetooth
import androidx.compose.material.icons.filled.CallReceived
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.QrCode
import androidx.compose.material.icons.filled.QrCodeScanner
import androidx.compose.material.icons.filled.Receipt
import androidx.compose.material.icons.filled.Send
import androidx.compose.material.icons.filled.SwapHoriz
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.rotm.MeshManager
import com.example.rotm.Transaction
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions

private val GradientBg = Brush.verticalGradient(
    colors = listOf(Color(0xFF0F0C29), Color(0xFF302B63), Color(0xFF24243E))
)
private val AccentGreen = Color(0xFF00E676)
private val AccentPurple = Color(0xFF7C4DFF)
private val CardBg = Color(0xFF1E1B33)
private val NavBg = Color(0xFF17142A)

@Composable
fun WalletScreen(mesh: MeshManager) {
    val context = LocalContext.current

    var balance by remember { mutableStateOf(0.0) }
    var isScanning by remember { mutableStateOf(false) }
    var showSendSheet by remember { mutableStateOf(false) }
    var showReceiveSheet by remember { mutableStateOf(false) }
    var prefillReceiver by remember { mutableStateOf("") }
    var publicKey by remember { mutableStateOf<String?>(null) }
    var history by remember { mutableStateOf<List<Transaction>>(emptyList()) }
    var selectedTab by remember { mutableStateOf(0) }

    fun refresh() {
        publicKey?.let {
            balance = mesh.balanceOf(it)
            history = mesh.transactionHistory(it)
        }
    }

    LaunchedEffect(Unit) {
        val kp = mesh.initWallet()
        publicKey = kp.publicKeyHex
        refresh()
    }

    val scanLauncher = rememberLauncherForActivityResult(ScanContract()) { result ->
        if (result.contents != null) {
            prefillReceiver = result.contents
            showSendSheet = true
        }
    }

    fun launchScanner() {
        val options = ScanOptions()
        options.setDesiredBarcodeFormats(ScanOptions.QR_CODE)
        options.setPrompt("Scan a ROTM QR code")
        options.setBeepEnabled(true)
        options.setOrientationLocked(true)
        scanLauncher.launch(options)
    }

    Scaffold(
        containerColor = Color.Transparent,
        bottomBar = {
            BottomNavBar(
                selectedTab = selectedTab,
                onTabSelected = { selectedTab = it },
                onScanClick = { launchScanner() }
            )
        }
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(GradientBg)
                .padding(padding)
        ) {
            when (selectedTab) {
                0 -> HomeTab(
                    balance = balance,
                    isScanning = isScanning,
                    history = history,
                    publicKey = publicKey.orEmpty(),
                    onSendClick = { prefillReceiver = ""; showSendSheet = true },
                    onReceiveClick = { showReceiveSheet = true },
                    onScanClick = { launchScanner() },
                    onReceiveActionClick = {
                        isScanning = true
                        mesh.startReceiving()
                    }
                )
                1 -> ActivityTab(history = history, publicKey = publicKey.orEmpty())
                2 -> ProfileTab(publicKey = publicKey.orEmpty())
            }

            if (showSendSheet) {
                SendSheet(
                    initialReceiver = prefillReceiver,
                    onDismiss = { showSendSheet = false },
                    onScanClick = { launchScanner() },
                    onSend = { receiver, amount ->
                        showSendSheet = false
                        mesh.sendPayment(receiver, amount) { success ->
                            refresh()
                            val msg = if (success) "Payment sent!" else "Payment failed"
                            Toast.makeText(context, msg, Toast.LENGTH_SHORT).show()
                        }
                    }
                )
            }

            if (showReceiveSheet) {
                ReceiveSheet(
                    publicKey = publicKey.orEmpty(),
                    onDismiss = { showReceiveSheet = false }
                )
            }
        }
    }
}

@Composable
private fun HomeTab(
    balance: Double,
    isScanning: Boolean,
    history: List<Transaction>,
    publicKey: String,
    onSendClick: () -> Unit,
    onReceiveClick: () -> Unit,
    onScanClick: () -> Unit,
    onReceiveActionClick: () -> Unit
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 20.dp)
    ) {
        Spacer(Modifier.height(20.dp))

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column {
                Text("ROTM", color = Color.White, fontSize = 30.sp, fontWeight = FontWeight.Black)
                Text(
                    "Offline Payments Mesh",
                    color = Color.White.copy(alpha = 0.5f),
                    fontSize = 12.sp
                )
            }
            Surface(
                shape = CircleShape,
                color = Color.White.copy(alpha = 0.08f),
                modifier = Modifier.size(44.dp)
            ) {
                Icon(
                    Icons.Default.AccountCircle,
                    contentDescription = "Profile",
                    tint = Color.White.copy(alpha = 0.8f),
                    modifier = Modifier.padding(8.dp)
                )
            }
        }

        Spacer(Modifier.height(20.dp))

        BalanceCard(balance = balance)

        Spacer(Modifier.height(20.dp))

        // Quick actions grid, PhonePe style
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            QuickAction(icon = Icons.Default.QrCodeScanner, label = "Scan & Pay", color = AccentPurple, onClick = onScanClick)
            QuickAction(icon = Icons.Default.Send, label = "Send", color = AccentPurple, onClick = onSendClick)
            QuickAction(icon = Icons.Default.CallReceived, label = "Receive", color = AccentGreen, onClick = onReceiveClick)
            QuickAction(
                icon = Icons.Default.Bluetooth,
                label = if (isScanning) "Waiting…" else "Go Online",
                color = AccentGreen,
                pulsing = isScanning,
                onClick = onReceiveActionClick
            )
        }

        Spacer(Modifier.height(28.dp))

        Text(
            "Recent Activity",
            color = Color.White.copy(alpha = 0.8f),
            fontSize = 16.sp,
            fontWeight = FontWeight.Bold
        )

        Spacer(Modifier.height(12.dp))

        if (history.isEmpty()) {
            EmptyState()
        } else {
            LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                items(history.take(6)) { tx ->
                    TransactionRow(tx = tx, myKey = publicKey)
                }
            }
        }
    }
}

@Composable
private fun ActivityTab(history: List<Transaction>, publicKey: String) {
    Column(modifier = Modifier.fillMaxSize().padding(20.dp)) {
        Text("Activity", color = Color.White, fontSize = 26.sp, fontWeight = FontWeight.Black)
        Spacer(Modifier.height(20.dp))
        if (history.isEmpty()) {
            EmptyState()
        } else {
            LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                items(history) { tx ->
                    TransactionRow(tx = tx, myKey = publicKey)
                }
            }
        }
    }
}

@Composable
private fun ProfileTab(publicKey: String) {
    val clipboard = LocalClipboardManager.current
    val context = LocalContext.current

    Column(
        modifier = Modifier.fillMaxSize().padding(20.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Spacer(Modifier.height(20.dp))
        Text("Profile", color = Color.White, fontSize = 26.sp, fontWeight = FontWeight.Black, modifier = Modifier.align(Alignment.Start))
        Spacer(Modifier.height(24.dp))

        Surface(shape = CircleShape, color = AccentPurple.copy(alpha = 0.2f), modifier = Modifier.size(80.dp)) {
            Icon(Icons.Default.AccountCircle, contentDescription = null, tint = AccentPurple, modifier = Modifier.padding(14.dp))
        }

        Spacer(Modifier.height(20.dp))
        Text("Your Wallet Address", color = Color.White.copy(alpha = 0.6f), fontSize = 13.sp)
        Spacer(Modifier.height(6.dp))

        Surface(
            shape = RoundedCornerShape(14.dp),
            color = CardBg,
            modifier = Modifier.fillMaxWidth()
        ) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(16.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    publicKey.take(28) + "…",
                    color = Color.White,
                    fontSize = 13.sp,
                    modifier = Modifier.weight(1f)
                )
                Icon(
                    Icons.Default.ContentCopy,
                    contentDescription = "Copy",
                    tint = AccentPurple,
                    modifier = Modifier.size(20.dp)
                )
            }
        }

        Spacer(Modifier.height(16.dp))
        Button(
            onClick = {
                clipboard.setText(AnnotatedString(publicKey))
                Toast.makeText(context, "Address copied", Toast.LENGTH_SHORT).show()
            },
            colors = ButtonDefaults.buttonColors(containerColor = AccentPurple),
            modifier = Modifier.fillMaxWidth().height(50.dp)
        ) {
            Text("Copy Address")
        }

        Spacer(Modifier.height(24.dp))
        Text(
            "ROTM \u2014 Research prototype. Balances are simulated, not real currency, unless connected to a payment provider.",
            color = Color.White.copy(alpha = 0.4f),
            fontSize = 11.sp
        )
    }
}

@Composable
private fun BottomNavBar(selectedTab: Int, onTabSelected: (Int) -> Unit, onScanClick: () -> Unit) {
    Surface(color = NavBg) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .navigationBarsPadding()
                .height(64.dp)
                .padding(horizontal = 8.dp),
            horizontalArrangement = Arrangement.SpaceEvenly,
            verticalAlignment = Alignment.CenterVertically
        ) {
            NavItem(icon = Icons.Default.Home, label = "Home", selected = selectedTab == 0) { onTabSelected(0) }

            Surface(
                onClick = onScanClick,
                shape = CircleShape,
                color = AccentPurple,
                modifier = Modifier.size(52.dp).offset(y = (-8).dp)
            ) {
                Icon(
                    Icons.Default.QrCodeScanner,
                    contentDescription = "Scan",
                    tint = Color.White,
                    modifier = Modifier.padding(13.dp)
                )
            }

            NavItem(icon = Icons.Default.Receipt, label = "Activity", selected = selectedTab == 1) { onTabSelected(1) }
        }
    }
}

@Composable
private fun NavItem(icon: ImageVector, label: String, selected: Boolean, onClick: () -> Unit) {
    val color = if (selected) AccentPurple else Color.White.copy(alpha = 0.4f)
    Surface(
        onClick = onClick,
        color = Color.Transparent,
        shape = RoundedCornerShape(12.dp)
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier.padding(8.dp)
        ) {
            Icon(icon, contentDescription = label, tint = color, modifier = Modifier.size(22.dp))
            Spacer(Modifier.height(2.dp))
            Text(label, color = color, fontSize = 10.sp)
        }
    }
}

@Composable
private fun QuickAction(icon: ImageVector, label: String, color: Color, pulsing: Boolean = false, onClick: () -> Unit) {
    val infinite = rememberInfiniteTransition(label = "pulse")
    val scale by infinite.animateFloat(
        initialValue = 1f,
        targetValue = if (pulsing) 1.1f else 1f,
        animationSpec = infiniteRepeatable(tween(700), RepeatMode.Reverse),
        label = "scale"
    )

    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Surface(
            onClick = onClick,
            shape = CircleShape,
            color = color.copy(alpha = 0.15f),
            modifier = Modifier.size(56.dp).scale(if (pulsing) scale else 1f)
        ) {
            Icon(icon, contentDescription = label, tint = color, modifier = Modifier.padding(15.dp))
        }
        Spacer(Modifier.height(6.dp))
        Text(label, color = Color.White.copy(alpha = 0.8f), fontSize = 11.sp)
    }
}

@Composable
private fun BalanceCard(balance: Double) {
    val animatedBalance by animateFloatAsState(
        targetValue = balance.toFloat(),
        animationSpec = tween(durationMillis = 900, easing = FastOutSlowInEasing),
        label = "balance"
    )

    val infinite = rememberInfiniteTransition(label = "glow")
    val glowAlpha by infinite.animateFloat(
        initialValue = 0.15f,
        targetValue = 0.35f,
        animationSpec = infiniteRepeatable(tween(2000), RepeatMode.Reverse),
        label = "glowAlpha"
    )

    Box(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(24.dp))
            .background(
                Brush.linearGradient(listOf(AccentPurple.copy(alpha = glowAlpha + 0.5f), CardBg))
            )
            .padding(24.dp)
    ) {
        Column {
            Text("Balance", color = Color.White.copy(alpha = 0.7f), fontSize = 14.sp)
            Spacer(Modifier.height(6.dp))
            Text(
                "\u20b9${"%.2f".format(animatedBalance)}",
                color = Color.White,
                fontSize = 40.sp,
                fontWeight = FontWeight.ExtraBold
            )
        }
    }
}

@Composable
private fun TransactionRow(tx: Transaction, myKey: String) {
    val isOutgoing = tx.senderPublicKey == myKey
    val sign = if (isOutgoing) "-" else "+"
    val color = if (isOutgoing) Color(0xFFFF5252) else AccentGreen

    var visible by remember { mutableStateOf(false) }
    LaunchedEffect(tx.txId) { visible = true }

    AnimatedVisibility(
        visible = visible,
        enter = fadeIn(tween(400)) + slideInVertically(tween(400)) { it / 3 }
    ) {
        Surface(shape = RoundedCornerShape(14.dp), color = CardBg, modifier = Modifier.fillMaxWidth()) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(16.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text(if (isOutgoing) "Sent" else "Received", color = Color.White, fontWeight = FontWeight.Medium)
                    Text(
                        (if (isOutgoing) tx.receiverPublicKey else tx.senderPublicKey).take(16) + "…",
                        color = Color.White.copy(alpha = 0.5f),
                        fontSize = 12.sp
                    )
                }
                Text("$sign\u20b9${"%.2f".format(tx.amount)}", color = color, fontWeight = FontWeight.Bold)
            }
        }
    }
}

@Composable
private fun EmptyState() {
    Column(
        modifier = Modifier.fillMaxWidth().padding(top = 40.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Icon(
            Icons.Default.SwapHoriz,
            contentDescription = null,
            tint = Color.White.copy(alpha = 0.2f),
            modifier = Modifier.size(48.dp)
        )
        Spacer(Modifier.height(8.dp))
        Text("No transactions yet", color = Color.White.copy(alpha = 0.4f))
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SendSheet(
    initialReceiver: String,
    onDismiss: () -> Unit,
    onScanClick: () -> Unit,
    onSend: (String, Double) -> Unit
) {
    var receiver by remember { mutableStateOf(initialReceiver) }
    var amountText by remember { mutableStateOf("") }

    LaunchedEffect(initialReceiver) { receiver = initialReceiver }

    ModalBottomSheet(onDismissRequest = onDismiss, containerColor = CardBg) {
        Column(modifier = Modifier.padding(24.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text("Send Payment", color = Color.White, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                Surface(
                    onClick = onScanClick,
                    shape = CircleShape,
                    color = AccentPurple.copy(alpha = 0.15f),
                    modifier = Modifier.size(40.dp)
                ) {
                    Icon(Icons.Default.QrCode, contentDescription = "Scan", tint = AccentPurple, modifier = Modifier.padding(9.dp))
                }
            }
            Spacer(Modifier.height(20.dp))

            OutlinedTextField(
                value = receiver,
                onValueChange = { receiver = it },
                label = { Text("Receiver public key") },
                modifier = Modifier.fillMaxWidth(),
                colors = OutlinedTextFieldDefaults.colors(focusedTextColor = Color.White, unfocusedTextColor = Color.White)
            )
            Spacer(Modifier.height(12.dp))
            OutlinedTextField(
                value = amountText,
                onValueChange = { amountText = it },
                label = { Text("Amount") },
                modifier = Modifier.fillMaxWidth(),
                colors = OutlinedTextFieldDefaults.colors(focusedTextColor = Color.White, unfocusedTextColor = Color.White)
            )
            Spacer(Modifier.height(20.dp))

            Button(
                onClick = {
                    val amount = amountText.toDoubleOrNull() ?: return@Button
                    if (receiver.isNotBlank()) onSend(receiver, amount)
                },
                modifier = Modifier.fillMaxWidth().height(52.dp),
                colors = ButtonDefaults.buttonColors(containerColor = AccentPurple)
            ) {
                Text("Send")
            }
            Spacer(Modifier.height(12.dp))
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ReceiveSheet(publicKey: String, onDismiss: () -> Unit) {
    val clipboard = LocalClipboardManager.current
    val context = LocalContext.current
    val qrBitmap = remember(publicKey) { generateQrBitmap(publicKey) }

    ModalBottomSheet(onDismissRequest = onDismiss, containerColor = CardBg) {
        Column(
            modifier = Modifier.padding(24.dp).fillMaxWidth(),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text("Receive Payment", color = Color.White, fontSize = 20.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(20.dp))

            Surface(shape = RoundedCornerShape(16.dp), color = Color.White, modifier = Modifier.size(220.dp)) {
                Image(
                    bitmap = qrBitmap.asImageBitmap(),
                    contentDescription = "Your QR code",
                    modifier = Modifier.padding(12.dp)
                )
            }

            Spacer(Modifier.height(16.dp))
            Text(
                publicKey.take(28) + "…",
                color = Color.White.copy(alpha = 0.6f),
                fontSize = 12.sp
            )

            Spacer(Modifier.height(16.dp))
            Button(
                onClick = {
                    clipboard.setText(AnnotatedString(publicKey))
                    Toast.makeText(context, "Address copied", Toast.LENGTH_SHORT).show()
                },
                colors = ButtonDefaults.buttonColors(containerColor = AccentPurple),
                modifier = Modifier.fillMaxWidth().height(50.dp)
            ) {
                Text("Copy Address")
            }
            Spacer(Modifier.height(12.dp))
        }
    }
}
