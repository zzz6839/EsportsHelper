from time import sleep
from traceback import format_exc
from rich import print
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait
from EsportsHelper.Logger import log
from EsportsHelper.Config import config
from EsportsHelper.I18n import i18n
from EsportsHelper.Stats import stats
from EsportsHelper.Utils import formatExc, debugScreen

_ = i18n.getText
_log = i18n.getLog


def unmuteStream(muteButton) -> None:
    """
    Unmute the stream by clicking the given mute button. If the click fails,
    executes a JavaScript click to try again. Also prints a message to the console
    and logs the action to the application log.

    Args:
        muteButton (WebElement): The mute button element to click.

    Returns:
        None
    """
    try:
        muteButton.click()
        log.info(_log("Youtube: 解除静音成功"))
    except Exception:
        log.error(_log("Youtube: 解除静音失败"))
        log.error(formatExc(format_exc()))


def playStream(playButton) -> None:
    """
    Clicks on the play button of a stream.

    Args:
        playButton: WebElement - The WebElement corresponding to the play button of the stream.

    Returns:
        None
    """
    try:
        playButton.click()
        log.info(_log("Youtube: 解除暂停成功"))
    except Exception:
        log.error(_log("Youtube: 解除暂停失败"))
        log.error(formatExc(format_exc()))


class YouTube:
    def __init__(self, driver) -> None:
        self.driver = driver
        self.wait = WebDriverWait(self.driver, 20)

    def checkYoutubeStream(self) -> bool:
        """
        This function checks if the YouTube livestream can be played, and resumes playing or unmute the video if it is paused or muted.

        Returns:
            bool: Returns True if the check is successful, otherwise returns False.
        """
        if config.closeStream:
            return True
        try:
            self.wait.until(ec.frame_to_be_available_and_switch_to_it(
                (By.CSS_SELECTOR, "iframe[id=video-player-youtube]")))
            # If a video mute is detected, unmute it
            muteButton = self.wait.until(ec.presence_of_element_located(
                (By.CSS_SELECTOR, "button.ytp-mute-button.ytp-button")))
            if muteButton.get_attribute("data-title-no-tooltip") == "Unmute":
                debugScreen(self.driver, lint="Unmute")
                unmuteStream(muteButton)
            # Play if a video pause is detected
            playButton = self.wait.until(ec.presence_of_element_located(
                (By.CSS_SELECTOR, "button.ytp-play-button.ytp-button")))
            if playButton.get_attribute("data-title-no-tooltip") == "Play":
                debugScreen(self.driver, lint="Play")
                playStream(playButton)
            self.driver.switch_to.default_content()
            return True
        except Exception:
            log.error(_log("Youtube: 检查直播发生错误"))
            log.error(formatExc(format_exc()))
            self.driver.switch_to.default_content()
            return False

    def setYoutubeQuality(self) -> bool:
        """
        Sets the video quality of a YouTube video being played.

        Returns:
        bool: True if the operation is successful, False otherwise.
        """
        try:
            self.wait.until(ec.frame_to_be_available_and_switch_to_it(
                (By.CSS_SELECTOR, "iframe[id=video-player-youtube]")))
            settingsButton = self.wait.until(ec.presence_of_element_located(
                (By.CSS_SELECTOR, "button.ytp-button.ytp-settings-button")))
            self.driver.execute_script("arguments[0].click();", settingsButton)
            sleep(1)
            try:
                qualityButton = self.wait.until(ec.presence_of_element_located(
                    (By.CSS_SELECTOR, "div.ytp-panel > div.ytp-panel-menu > div:nth-child(3)")))
            except Exception:
                qualityButton = self.wait.until(ec.presence_of_element_located(
                    (By.CSS_SELECTOR, "div.ytp-panel > div.ytp-panel-menu > div:nth-child(2)")))
            self.driver.execute_script("arguments[0].click();", qualityButton)
            sleep(1)
            option = self.wait.until(ec.presence_of_element_located(
                (By.CSS_SELECTOR, "div.ytp-panel.ytp-quality-menu > div.ytp-panel-menu > div:nth-last-child(2)")))
            self.driver.execute_script("arguments[0].click();", option)
            self.driver.switch_to.default_content()
            return True
        except Exception:
            self.driver.switch_to.default_content()
            log.error(_log("Youtube: 设置清晰度时发生错误"))
            log.error(formatExc(format_exc()))
            debugScreen(self.driver, lint="youtubeQuality")
            return False
