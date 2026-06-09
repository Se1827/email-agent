package com.emailagent.wear.ui.screen

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.wear.compose.foundation.lazy.ScalingLazyColumn
import androidx.wear.compose.foundation.lazy.rememberScalingLazyListState
import androidx.wear.compose.material.Chip
import androidx.wear.compose.material.ChipDefaults
import androidx.wear.compose.material.MaterialTheme
import androidx.wear.compose.material.PositionIndicator
import androidx.wear.compose.material.Scaffold
import androidx.wear.compose.material.Text
import androidx.wear.compose.material.TimeText
import androidx.wear.compose.material.Vignette
import androidx.wear.compose.material.VignettePosition
import com.emailagent.wear.data.model.EmailItem

private const val LABEL_SEND = "✓ Send"
private const val LABEL_SKIP = "✗ Skip"
private const val LABEL_DRAFT_REPLY = "Draft Reply"

private val SendChipBackground = Color(0xFF6366F1)
private val SkipChipBackground = Color(0xFF2A2E3F)
private val CategoryBadgeBackground = Color(0xFF2A2E3F)
private val CategoryBadgeTextColor = Color(0xFF9CA3AF)
private val DividerColor = Color(0xFF2A2E3F)

@Composable
fun EmailDetailScreen(
    emailItem: EmailItem,
    onSend: () -> Unit,
    onSkip: () -> Unit
) {
    val listState = rememberScalingLazyListState()

    Scaffold(
        timeText = { TimeText() },
        vignette = { Vignette(vignettePosition = VignettePosition.TopAndBottom) },
        positionIndicator = { PositionIndicator(scalingLazyListState = listState) }
    ) {
        ScalingLazyColumn(
            state = listState,
            modifier = Modifier.fillMaxSize(),
            verticalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            item {
                Text(
                    text = emailItem.senderDisplayName,
                    style = MaterialTheme.typography.title1,
                    textAlign = TextAlign.Center,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp)
                )
            }

            item {
                Text(
                    text = emailItem.category.uppercase(),
                    style = MaterialTheme.typography.caption2.copy(color = CategoryBadgeTextColor),
                    modifier = Modifier
                        .clip(RoundedCornerShape(4.dp))
                        .background(CategoryBadgeBackground)
                        .padding(horizontal = 6.dp, vertical = 2.dp)
                )
            }

            item {
                Spacer(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp)
                        .height(1.dp)
                        .background(DividerColor)
                )
            }

            item {
                Text(
                    text = LABEL_DRAFT_REPLY,
                    style = MaterialTheme.typography.caption1.copy(color = SendChipBackground),
                    modifier = Modifier.padding(horizontal = 16.dp)
                )
            }

            item {
                Text(
                    text = emailItem.fullDraftBody,
                    style = MaterialTheme.typography.body2,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp)
                )
            }

            item {
                Spacer(modifier = Modifier.height(4.dp))
            }

            item {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 12.dp),
                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    Chip(
                        onClick = onSend,
                        colors = ChipDefaults.chipColors(
                            backgroundColor = SendChipBackground,
                            contentColor = Color.White
                        ),
                        label = {
                            Text(
                                text = LABEL_SEND,
                                style = MaterialTheme.typography.caption1.copy(color = Color.White),
                                maxLines = 1
                            )
                        },
                        modifier = Modifier
                            .weight(1f)
                            .height(36.dp)
                    )
                    Chip(
                        onClick = onSkip,
                        colors = ChipDefaults.chipColors(
                            backgroundColor = SkipChipBackground,
                            contentColor = CategoryBadgeTextColor
                        ),
                        label = {
                            Text(
                                text = LABEL_SKIP,
                                style = MaterialTheme.typography.caption1.copy(color = CategoryBadgeTextColor),
                                maxLines = 1
                            )
                        },
                        modifier = Modifier
                            .weight(1f)
                            .height(36.dp)
                    )
                }
            }

            item {
                Spacer(modifier = Modifier.height(16.dp))
            }
        }
    }
}
