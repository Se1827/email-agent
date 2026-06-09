package com.emailagent.wear.ui.screen

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Warning
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.wear.compose.foundation.lazy.ScalingLazyColumn
import androidx.wear.compose.foundation.lazy.items
import androidx.wear.compose.foundation.lazy.rememberScalingLazyListState
import androidx.wear.compose.material.Chip
import androidx.wear.compose.material.ChipDefaults
import androidx.wear.compose.material.CircularProgressIndicator
import androidx.wear.compose.material.Icon
import androidx.wear.compose.material.MaterialTheme
import androidx.wear.compose.material.PositionIndicator
import androidx.wear.compose.material.Scaffold
import androidx.wear.compose.material.Text
import androidx.wear.compose.material.TimeText
import androidx.wear.compose.material.Vignette
import androidx.wear.compose.material.VignettePosition
import com.emailagent.wear.ui.components.EmailCard
import com.emailagent.wear.viewmodel.EmailUiState
import com.emailagent.wear.viewmodel.EmailViewModel
import kotlinx.coroutines.delay

private const val LABEL_CHECKING_DRAFTS = "Checking drafts…"
private const val LABEL_BACKEND_WAKING = "Backend waking up, please wait…"
private const val LABEL_ALL_CAUGHT_UP = "All caught up!"
private const val LABEL_NO_PENDING = "No pending replies"
private const val LABEL_REFRESH = "Refresh"
private const val LABEL_AUTO_REFRESH_PREFIX = "Auto-refresh in "
private const val LABEL_AUTO_REFRESH_SUFFIX = "s"
private const val LABEL_AUTO_REFRESHES = "Auto-refreshes every 30s"
private const val LABEL_RETRY = "Retry"
private const val LABEL_RENDER_HINT = "Render free tier may take ~30s"

private const val COLD_START_DELAY_MS = 5000L
private const val POLL_COUNTDOWN_SECONDS = 30
private const val COUNTDOWN_TICK_MS = 1000L

private val AccentIndigo = Color(0xFF6366F1)
private val WarningOrange = Color(0xFFF97316)
private val MutedGray = Color(0xFF6B7280)

@Composable
fun EmailListScreen(
    viewModel: EmailViewModel,
    onEmailClick: (String) -> Unit
) {
    val uiState by viewModel.uiState.collectAsState()

    val listState = rememberScalingLazyListState()

    Scaffold(
        timeText = { TimeText() },
        vignette = { Vignette(vignettePosition = VignettePosition.TopAndBottom) },
        positionIndicator = { PositionIndicator(scalingLazyListState = listState) }
    ) {
        when (val state = uiState) {
            is EmailUiState.Loading -> LoadingContent()
            is EmailUiState.Empty -> EmptyContent(onRefresh = { viewModel.refreshNow() })
            is EmailUiState.Success -> {
                ScalingLazyColumn(
                    state = listState,
                    modifier = Modifier.fillMaxSize(),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    items(
                        items = state.emails,
                        key = { it.id }
                    ) { email ->
                        EmailCard(
                            item = email,
                            onSendClick = { viewModel.approveDraft(email.id) },
                            onSkipClick = { viewModel.dismissLocally(email.id) },
                            onCardClick = { onEmailClick(email.id) },
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = 8.dp)
                        )
                    }
                    item {
                        Text(
                            text = LABEL_AUTO_REFRESHES,
                            style = MaterialTheme.typography.caption2.copy(color = MutedGray),
                            textAlign = TextAlign.Center,
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(top = 4.dp, bottom = 16.dp)
                        )
                    }
                }
            }
            is EmailUiState.Error -> ErrorContent(
                message = state.message,
                onRetry = { viewModel.refreshNow() }
            )
        }
    }
}

@Composable
private fun LoadingContent() {
    var showColdStartHint by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        delay(COLD_START_DELAY_MS)
        showColdStartHint = true
    }

    Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            CircularProgressIndicator(
                modifier = Modifier.size(32.dp),
                indicatorColor = AccentIndigo,
                strokeWidth = 3.dp
            )
            Spacer(modifier = Modifier.height(12.dp))
            Text(
                text = LABEL_CHECKING_DRAFTS,
                style = MaterialTheme.typography.body2,
                textAlign = TextAlign.Center
            )
            if (showColdStartHint) {
                Spacer(modifier = Modifier.height(6.dp))
                Text(
                    text = LABEL_BACKEND_WAKING,
                    style = MaterialTheme.typography.caption2.copy(color = MutedGray),
                    textAlign = TextAlign.Center
                )
            }
        }
    }
}

@Composable
private fun EmptyContent(onRefresh: () -> Unit) {
    var countdown by remember { mutableIntStateOf(POLL_COUNTDOWN_SECONDS) }

    LaunchedEffect(Unit) {
        while (true) {
            delay(COUNTDOWN_TICK_MS)
            countdown = if (countdown > 1) countdown - 1 else POLL_COUNTDOWN_SECONDS
        }
    }

    Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
            modifier = Modifier.padding(horizontal = 24.dp)
        ) {
            Icon(
                imageVector = Icons.Default.CheckCircle,
                contentDescription = null,
                tint = AccentIndigo,
                modifier = Modifier.size(36.dp)
            )
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = LABEL_ALL_CAUGHT_UP,
                style = MaterialTheme.typography.title2,
                textAlign = TextAlign.Center
            )
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = LABEL_NO_PENDING,
                style = MaterialTheme.typography.body2,
                textAlign = TextAlign.Center
            )
            Spacer(modifier = Modifier.height(12.dp))
            Chip(
                onClick = onRefresh,
                colors = ChipDefaults.chipColors(
                    backgroundColor = AccentIndigo,
                    contentColor = Color.White
                ),
                label = {
                    Text(
                        text = LABEL_REFRESH,
                        style = MaterialTheme.typography.body2.copy(color = Color.White)
                    )
                },
                icon = {
                    Icon(
                        imageVector = Icons.Default.Refresh,
                        contentDescription = null,
                        tint = Color.White,
                        modifier = Modifier.size(16.dp)
                    )
                },
                modifier = Modifier.height(40.dp)
            )
            Spacer(modifier = Modifier.height(6.dp))
            Text(
                text = "$LABEL_AUTO_REFRESH_PREFIX$countdown$LABEL_AUTO_REFRESH_SUFFIX",
                style = MaterialTheme.typography.caption2.copy(color = MutedGray),
                textAlign = TextAlign.Center
            )
        }
    }
}

@Composable
private fun ErrorContent(
    message: String,
    onRetry: () -> Unit
) {
    val showRenderHint = message.contains("waking up", ignoreCase = true) ||
                         message.contains("timed out", ignoreCase = true)

    Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
            modifier = Modifier.padding(horizontal = 20.dp)
        ) {
            Icon(
                imageVector = Icons.Default.Warning,
                contentDescription = null,
                tint = WarningOrange,
                modifier = Modifier.size(32.dp)
            )
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = message,
                style = MaterialTheme.typography.body2,
                textAlign = TextAlign.Center,
                maxLines = 3
            )
            if (showRenderHint) {
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = LABEL_RENDER_HINT,
                    style = MaterialTheme.typography.caption2.copy(color = MutedGray),
                    textAlign = TextAlign.Center
                )
            }
            Spacer(modifier = Modifier.height(12.dp))
            Chip(
                onClick = onRetry,
                colors = ChipDefaults.chipColors(
                    backgroundColor = WarningOrange,
                    contentColor = Color.White
                ),
                label = {
                    Text(
                        text = LABEL_RETRY,
                        style = MaterialTheme.typography.body2.copy(color = Color.White)
                    )
                },
                modifier = Modifier.height(40.dp)
            )
        }
    }
}
