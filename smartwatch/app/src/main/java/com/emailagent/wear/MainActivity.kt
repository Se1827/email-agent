package com.emailagent.wear

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.compose.runtime.Composable
import androidx.wear.compose.navigation.SwipeDismissableNavHost
import androidx.wear.compose.navigation.composable
import androidx.wear.compose.navigation.rememberSwipeDismissableNavController
import com.emailagent.wear.ui.screen.EmailDetailScreen
import com.emailagent.wear.ui.screen.EmailListScreen
import com.emailagent.wear.ui.theme.EmailAgentWearTheme
import com.emailagent.wear.viewmodel.EmailViewModel

private const val ROUTE_LIST = "list"
private const val ROUTE_DETAIL = "detail/{emailId}"
private const val ARG_EMAIL_ID = "emailId"

class MainActivity : ComponentActivity() {

    private val viewModel: EmailViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        installSplashScreen()
        super.onCreate(savedInstanceState)

        setContent {
            EmailAgentWearTheme {
                WearNavHost(viewModel = viewModel)
            }
        }
    }
}

@Composable
private fun WearNavHost(viewModel: EmailViewModel) {
    val navController = rememberSwipeDismissableNavController()

    SwipeDismissableNavHost(
        navController = navController,
        startDestination = ROUTE_LIST
    ) {
        composable(ROUTE_LIST) {
            EmailListScreen(
                viewModel = viewModel,
                onEmailClick = { emailId ->
                    navController.navigate("detail/$emailId")
                }
            )
        }

        composable(ROUTE_DETAIL) { backStackEntry ->
            val emailId = backStackEntry.arguments?.getString(ARG_EMAIL_ID) ?: return@composable
            val emailItem = viewModel.getEmailById(emailId) ?: return@composable

            EmailDetailScreen(
                emailItem = emailItem,
                onSend = {
                    viewModel.approveDraft(emailId)
                    navController.popBackStack()
                },
                onSkip = {
                    viewModel.dismissLocally(emailId)
                    navController.popBackStack()
                }
            )
        }
    }
}
