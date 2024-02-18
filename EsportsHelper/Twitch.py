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
        log.info(_log("Twitch: 解除暂停成功"))
    except Exception:
        log.error(_log("Twitch: 解除暂停失败"))
        log.error(formatExc(format_exc()))


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
        log.info(_log("Twitch: 解除静音成功"))
    except Exception:
        log.error(_log("Twitch: 解除静音失败"))
        log.error(formatExc(format_exc()))


class Twitch:
    def __init__(self, driver) -> None:
        self.driver = driver
        self.wait = WebDriverWait(self.driver, 25)

    def setTwitchQuality(self) -> bool:
        """
        Sets the quality of the Twitch video player to the lowest available option and unmute the audio.

        Returns:
            True if the operation is successful, False otherwise.
        """
        try:
            self.wait.until(ec.frame_to_be_available_and_switch_to_it(
                (By.CSS_SELECTOR, "iframe[title=Twitch]")))
            sleep(1)
            settingsButton = self.wait.until(ec.presence_of_element_located(
                (By.CSS_SELECTOR, "button[data-a-target=player-settings-button]")))
            self.driver.execute_script("arguments[0].click();", settingsButton)
            sleep(1)
            qualityButton = self.wait.until(ec.presence_of_element_located(
                (By.CSS_SELECTOR, "button[data-a-target=player-settings-menu-item-quality]")))
            self.driver.execute_script("arguments[0].click();", qualityButton)
            sleep(1)
            options = self.wait.until(ec.presence_of_all_elements_located(
                (By.CSS_SELECTOR, "input[data-a-target=tw-radio]")))
            self.driver.execute_script("arguments[0].click();", options[-1])
            sleep(1)
            self.driver.switch_to.default_content()
            return True
        except Exception:
            log.error(_log("Twitch: 设置清晰度发生错误"))
            log.error(formatExc(format_exc()))
            debugScreen(self.driver, lint="setTwitchQuality")
        self.driver.switch_to.default_content()
        return False

    def checkTwitchStream(self) -> bool:
        """
        Checks the status of the Twitch stream.

        Returns:
            bool: True if the stream is active and playable, False otherwise.
        """
        if config.closeStream:
            return True
        try:
            self.wait.until(ec.frame_to_be_available_and_switch_to_it(
                (By.CSS_SELECTOR, "iframe[title=Twitch]")))
            self.driver.implicitly_wait(5)
            sleep(2)
            errorInfo = self.driver.find_elements(By.CSS_SELECTOR, "div[data-a-target=player-overlay-content-gate]")
            if len(errorInfo) > 0:
                debugScreen(self.driver, lint="streamError")
                self.driver.switch_to.default_content()
                return False
            loading = self.driver.find_elements(By.CSS_SELECTOR, "div.Layout-sc-1xcs6mc-0.MIEJo.player-overlay-background > div")
            if len(loading) > 0:
                sleep(5)
                loading = self.driver.find_elements(By.CSS_SELECTOR, "div.Layout-sc-1xcs6mc-0.MIEJo.player-overlay-background > div")
                if len(loading) > 0:
                    sleep(10)
                    loading = self.driver.find_elements(By.CSS_SELECTOR, "div.Layout-sc-1xcs6mc-0.MIEJo.player-overlay-background > div")
                    if len(loading) > 0:
                        sleep(15)
                        loading = self.driver.find_elements(By.CSS_SELECTOR, "div.Layout-sc-1xcs6mc-0.MIEJo.player-overlay-background > div")
                        if len(loading) > 0:
                            debugScreen(self.driver, lint="streamLoading")
                            self.driver.switch_to.default_content()
                            return False
            self.driver.implicitly_wait(15)
            isMute = self.driver.find_elements(By.CSS_SELECTOR, "button[data-a-target=player-mute-unmute-button] > div > div > div > svg > g")
            muteButton = self.wait.until(ec.presence_of_element_located(
                (By.CSS_SELECTOR, "button[data-a-target=player-mute-unmute-button]")))
            if len(isMute) <= 0:
                debugScreen(self.driver, lint="unmute")
                unmuteStream(muteButton)
            playButton = self.wait.until(ec.presence_of_element_located(
                (By.CSS_SELECTOR, "button[data-a-target=player-play-pause-button]")))
            if playButton.get_attribute("data-a-player-state") == "paused":
                debugScreen(self.driver, lint="play")
                playStream(playButton)
            self.driver.switch_to.default_content()
            return True
        except Exception:
            log.error(_log("Twitch: 检查直播发生失败"))
            log.error(formatExc(format_exc()))
            debugScreen(self.driver, "rewardFailed")
        self.driver.switch_to.default_content()
        return False

    def checkTwitchIsOnline(self) -> int:
        """
        Checks the status of the Twitch stream.
        :return:
        """
        if config.closeStream:
            return 1
        try:
            self.wait.until(ec.frame_to_be_available_and_switch_to_it(
                (By.CSS_SELECTOR, "iframe[title=Twitch]")))
            self.driver.implicitly_wait(5)
            sleep(3)
            if len(self.driver.find_elements(By.CSS_SELECTOR, "span.offline-embeds--stylized-link")) > 0:
                debugScreen(self.driver, "offline")
                self.driver.switch_to.default_content()
                return -1
            self.driver.implicitly_wait(15)
            self.driver.switch_to.default_content()
            return 1
        except Exception:
            log.error(_log("Twitch: 检查直播间是否在线失败"))
            log.error(formatExc(format_exc()))
        self.driver.switch_to.default_content()
        return 0
