package com.emailagent.wear.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.emailagent.wear.data.model.EmailItem
import com.emailagent.wear.data.network.ApiClient
import com.emailagent.wear.data.network.EmailResponse
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

sealed class EmailUiState {
    data object Loading : EmailUiState()
    data object Empty : EmailUiState()
    data class Success(val emails: List<EmailItem>) : EmailUiState()
    data class Error(val message: String) : EmailUiState()
}

class EmailViewModel : ViewModel() {

    private val _uiState = MutableStateFlow<EmailUiState>(EmailUiState.Loading)
    val uiState: StateFlow<EmailUiState> = _uiState.asStateFlow()

    private val dismissedIds = mutableSetOf<String>()

    private var pollingJob: Job? = null

    companion object {
        private const val POLL_INTERVAL_MS = 30_000L
    }

    init {
        startPolling()
    }

    fun startPolling() {
        pollingJob?.cancel()
        pollingJob = viewModelScope.launch(Dispatchers.IO) {
            while (isActive) {
                fetchEmails()
                delay(POLL_INTERVAL_MS)
            }
        }
    }

    fun refreshNow() {
        viewModelScope.launch(Dispatchers.IO) {
            _uiState.value = EmailUiState.Loading
            fetchEmails()
        }
    }

    private suspend fun fetchEmails() {
        if (_uiState.value is EmailUiState.Error || _uiState.value is EmailUiState.Loading) {
            _uiState.value = EmailUiState.Loading
        }

        try {
            val response = ApiClient.emailService.getEmails()
            if (response.isSuccessful) {
                val allEmails = response.body() ?: emptyList()

                val pendingDrafts = allEmails
                    .filter { email ->
                        !email.draft_reply?.body.isNullOrBlank() &&
                        email.id !in dismissedIds
                    }
                    .map { it.toEmailItem() }

                _uiState.value = if (pendingDrafts.isEmpty()) {
                    EmailUiState.Empty
                } else {
                    EmailUiState.Success(pendingDrafts)
                }
            } else {
                _uiState.value = EmailUiState.Error("Server error: ${response.code()}")
            }
        } catch (e: java.net.SocketTimeoutException) {
            _uiState.value = EmailUiState.Error("Connection timed out.\nBackend may be waking up.")
        } catch (e: java.io.IOException) {
            _uiState.value = EmailUiState.Error("Network error.\nCheck Wi-Fi connection.")
        } catch (e: Exception) {
            _uiState.value = EmailUiState.Error("Unexpected error:\n${e.localizedMessage}")
        }
    }

    fun approveDraft(emailId: String) {
        viewModelScope.launch(Dispatchers.IO) {
            try {
                ApiClient.emailService.approveDraft(emailId)
                dismissLocally(emailId)
            } catch (_: Exception) {
                dismissLocally(emailId)
            }
        }
    }

    fun dismissLocally(emailId: String) {
        dismissedIds.add(emailId)
        val currentState = _uiState.value
        if (currentState is EmailUiState.Success) {
            val updated = currentState.emails.filter { it.id != emailId }
            _uiState.value = if (updated.isEmpty()) EmailUiState.Empty else EmailUiState.Success(updated)
        }
    }

    fun getEmailById(emailId: String): EmailItem? {
        val currentState = _uiState.value
        return if (currentState is EmailUiState.Success) {
            currentState.emails.find { it.id == emailId }
        } else {
            null
        }
    }

    override fun onCleared() {
        super.onCleared()
        pollingJob?.cancel()
    }
}

private fun EmailResponse.toEmailItem(): EmailItem {
    val draftBody = draft_reply?.body ?: ""
    val preview = if (draftBody.length > 60) draftBody.take(60) + "…" else draftBody

    return EmailItem(
        id = id,
        senderDisplayName = formatSender(sender),
        draftPreview = preview,
        fullDraftBody = draftBody,
        priority = classification?.priority ?: "normal",
        category = classification?.category ?: "info"
    )
}

private fun formatSender(email: String): String {
    val local = email.substringBefore("@")
    return if (local.contains(Regex("[._-]")) &&
               local != "noreply" &&
               local != "no-reply") {
        local.split(Regex("[._-]"))
             .joinToString(" ") { word ->
                 word.replaceFirstChar { it.uppercase() }
             }
    } else {
        email
    }
}
