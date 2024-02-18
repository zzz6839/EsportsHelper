import os
import time
from datetime import datetime, timedelta
from random import randint
from time import sleep
from traceback import format_exc

from retrying import retry

from EsportsHelper.Drop import Drop
from EsportsHelper.LiveDataProvider import fetchLiveMatches, checkNextMatch, fetchWatchRegions, fetchLeaguesId
from EsportsHelper.Logger import log
from EsportsHelper.Config import config
from EsportsHelper.NetworkHandler import NetworkHandler
from EsportsHelper.Rewards import Rewards
from EsportsHelper.Stats import stats
from EsportsHelper.Twitch import Twitch
from EsportsHelper.Utils import (OVERRIDES,
                                 getLolesportsWeb,
                                 getMatchName, sysQuit,
                                 getSleepPeriod,
                                 mouthTrans, timeTrans, formatExc,
                                 sortLiveList, updateLiveRegions, updateLiveRegionsColor,
                                 updateLiveDefinition, formatLeagueName, checkRewardPage, setTodayDropsNumber, debugScreen, errorNotify)
from EsportsHelper.YouTube import YouTube
from rich import print
from selenium.common import NoSuchElementException, NoSuchWindowException
from selenium.webdriver.common.by import By
from EsportsHelper.I18n import i18n

_ = i18n.getText
_log = i18n.getLog


class Match:
    def __init__(self, driver) -> None:
        self.driver = driver
        self.youtube = YouTube(driver=driver)
        self.twitch = Twitch(driver=driver)
        self.rewards = Rewards(driver=driver, youtube=self.youtube, twitch=self.twitch)
        self.networkHandler = NetworkHandler(driver=driver)
        self.currentWindows = {}
        self.rewardWindow = None
        self.mainWindow = self.driver.current_window_handle
        self.OVERRIDES = OVERRIDES
        self.sleepBeginList = []
        self.sleepEndList = []
        self.nextMatchHour = None
        self.nextMatchDay = None
        self.streamNumber = 0

    def watchMatches(self):
        """
        Watch live matches and earn rewards.
        """
        try:
            while stats.leaguesIdDict == {}:
                t = fetchLeaguesId()
            sleepFlag = False
            isSleep = False
            openDatetime = datetime.now()
            formattedOpenDatetime = openDatetime.strftime("%Y-%m-%d %H:%M:%S")
            self.currentWindows = {}
            self.mainWindow = self.driver.current_window_handle
            maxRunSecond = config.maxRunHours * 3600
            startTimePoint = time.time()
            endTimePoint = startTimePoint + maxRunSecond
            sleep(1)
            if config.connectorTest and config.connectorDropsUrl:
                if self.rewards.notifyDrops(Drop("Test", "", "", "", "", "", "", "", "")):
                    log.info(_log("测试通知成功"))
                    stats.info.append(f'{datetime.now().strftime("%H:%M:%S")} {_("测试通知成功", color="green")}')
                else:
                    log.info(_log("测试通知失败"))
                    stats.info.append(f'{datetime.now().strftime("%H:%M:%S")} {_("测试通知失败", color="red")}')

            if config.countDrops and sleepFlag is False:
                stats.status = _("初始化", color="yellow") + "[yellow]2[/yellow]"
                # Open the Rewards page
                self.rewardWindow = self.rewards.getRewardPage(newTab=True)
            # Gets the sleep period
            if config.sleepPeriod != [""]:
                self.sleepBeginList, self.sleepEndList = getSleepPeriod()
            if maxRunSecond > 0:
                stats.banner.append(_('结束时间: ', color='green') + time.strftime('%H:%M', time.localtime(endTimePoint)))

            while config.maxRunHours < 0 or time.time() < endTimePoint:
                sleep(1)
                self.driver.switch_to.window(self.mainWindow)
                stats.lastCheckTime = "[cyan]" + datetime.now().strftime('%H:%M:%S') + "[/cyan]"
                stats.nextCheckTime = ""
                stats.status = _("检查中", color="green")
                log.info(_log("开始检查..."))
                if checkNextMatch():
                    try:
                        self.nextMatchHour = int(stats.nextMatch.split("|")[1].split(' ')[1].split(":")[0])
                        self.nextMatchDay = int(stats.nextMatch.split("|")[1].split(' ')[0].split("-")[1])
                    except IndexError:
                        self.nextMatchHour = None
                        self.nextMatchDay = None
                        stats.nextMatch = _("暂无", color="green") + "|" + _("暂无", color="green")
                else:
                    self.nextMatchDay = None
                    self.checkNextMatch()
                # Random numbers, used for random delay
                randomDelay = randint(int(config.delay * 0.08), int(config.delay * 0.15))
                newDelay = randomDelay * 10
                nowTimeHour = int(time.localtime().tm_hour)
                nowTimeDay = int(time.localtime().tm_mday)
                liveUrlList = []
                sleepEndTime = ""
                # If you are not currently sleeping,
                # get match information (including matches that are still counting down).
                if isSleep is False:
                    log.info(_log("检查赛区直播状态..."))
                    liveUrlList = fetchLiveMatches(ignoreBroadCast=False, ignoreDisWatchMatches=True)
                    if liveUrlList == ["ERROR"]:
                        liveUrlList = self.getMatchInfo(ignoreBroadCast=False)
                if config.autoSleep:
                    # When the next game time is correct, go into sleep judgment.
                    if self.nextMatchHour is not None and self.nextMatchDay is not None:
                        # If the next match is on the same day as now, but the current time has exceeded the match time, sober up.
                        if nowTimeDay == self.nextMatchDay and \
                                nowTimeHour >= self.nextMatchHour:
                            isSleep = False
                        # If the next match is on the same day as the current day,
                        # and there is still over an hour before the match starts,
                        # and no regions are currently live-streaming, then enter a one-hour sleep mode.
                        elif nowTimeDay == self.nextMatchDay and \
                                nowTimeHour < self.nextMatchHour - 1 and \
                                self.currentWindows == {} and liveUrlList == []:
                            isSleep = True
                            newDelay = 3599
                        # If the next game is the same day as now, but the current time is already an hour before the game, sober up.
                        elif nowTimeDay == self.nextMatchDay and \
                                nowTimeHour == self.nextMatchHour - 1:
                            isSleep = False
                        # If the next game date is greater than the current date, and there is no live game now,
                        # and the current time hours are less than 23, sleep is entered with an interval of one hour.
                        elif nowTimeDay < self.nextMatchDay and self.currentWindows == {} \
                                and nowTimeHour < 23 and liveUrlList == []:
                            isSleep = True
                            newDelay = 3599
                        elif nowTimeDay < self.nextMatchDay and nowTimeHour >= 23:
                            isSleep = False
                        elif (nowTimeDay == 31 or nowTimeDay == 30 or nowTimeDay == 29) and \
                                (self.nextMatchDay == 1 or self.nextMatchDay == 2 or self.nextMatchDay == 3) \
                                and nowTimeHour < 23 and liveUrlList == []:
                            isSleep = True
                            newDelay = 3599
                        else:
                            isSleep = False
                    # Stay awake when the next game time is wrong.
                    else:
                        isSleep = False
                else:
                    if self.nextMatchHour is not None and self.nextMatchDay is not None:
                        if nowTimeDay < self.nextMatchDay and self.currentWindows == {} and nowTimeHour < 23 and liveUrlList == []:
                            newDelay = 3599
                        # When the time of the next game is longer than 1 hour from the current time, the check interval is one hour
                        elif nowTimeHour < self.nextMatchHour - 1 and self.currentWindows == {} and liveUrlList == []:
                            newDelay = 3599
                # The sleep period set has a higher priority than the autoSleep function.
                if self.sleepBeginList == [] and self.sleepEndList == []:
                    pass
                else:
                    nowTimeHour = int(time.localtime().tm_hour)
                    for sleepBegin, sleepEnd in zip(self.sleepBeginList, self.sleepEndList):
                        if sleepBegin <= nowTimeHour < sleepEnd:
                            if nowTimeHour < sleepEnd - 1:
                                newDelay = 3599
                            else:
                                randomDelay = randint(
                                    int(config.delay * 0.08), int(config.delay * 0.15))
                                newDelay = randomDelay * 10
                            isSleep = True
                            sleepEndTime = sleepEnd
                            break
                        else:
                            isSleep = False

                if isSleep:
                    if sleepFlag is False:
                        log.info(_log("进入休眠时间"))
                        stats.info.append(f"{datetime.now().strftime('%H:%M:%S')} " + _("进入休眠时间", color="green"))
                        stats.liveRegions = []
                        stats.status = _("休眠", color="yellow")
                        self.closeAllTabs()
                        sleepFlag = True
                    else:
                        log.info(_log("处于休眠时间..."))
                        stats.status = _("休眠", color="yellow")
                    if sleepEndTime:
                        wakeTime = sleepEndTime
                    else:
                        wakeTime = stats.nextMatch.split("|")[1]
                    log.info(f'{_log("预计休眠状态将持续到")} {wakeTime}')
                    if not any(f'{_("预计休眠状态将持续到", color="bold yellow")} [cyan]{wakeTime}[/cyan]' in info for info in stats.info):
                        stats.info.append(f"{datetime.now().strftime('%H:%M:%S')} " +
                                          f'{_("预计休眠状态将持续到", color="bold yellow")} [cyan]{wakeTime}[/cyan]')

                    log.info(
                        f"{_log('下次检查在:')} "
                        f"{(datetime.now() + timedelta(seconds=newDelay)).strftime('%m-%d %H:%M:%S')}")
                    stats.nextCheckTime = "[cyan]" + (datetime.now() + timedelta(seconds=newDelay)).strftime('%H:%M:%S') + "[/cyan]"
                    log.info(f"{'=' * 50}")
                    sleep(newDelay)
                    continue
                elif sleepFlag is True:
                    log.info(_log("休眠时间结束"))
                    stats.info.append(f"{datetime.now().strftime('%H:%M:%S')} " + _("休眠时间结束", color="green"))
                    stats.lastCheckTime = "[cyan]" + datetime.now().strftime('%H:%M:%S') + "[/cyan]"
                    stats.nextCheckTime = ""
                    stats.status = _("检查中", color="green")
                    log.info(_log("开始检查..."))
                    sleepFlag = False
                    if config.countDrops:
                        self.driver.switch_to.window(self.rewardWindow)
                        self.rewardWindow = self.rewards.getRewardPage()

                # Get the number of drops and total hours watched
                if config.countDrops:
                    watchRegion = fetchWatchRegions()
                    if watchRegion != "ERROR":
                        stats.watchRegion = watchRegion
                    else:
                        stats.watchRegion = _log("未知")
                    log.info(f"{_log('观看属地')}: {stats.watchRegion}")
                    self.driver.switch_to.window(self.rewardWindow)
                    checkRewardPage(self.driver, isInit=False)
                    setTodayDropsNumber()
                    self.rewards.checkNewDrops()
                    self.driver.switch_to.window(self.mainWindow)
                    if stats.currentWatchHour != "-1" and stats.currentDropsList != [" "]:
                        currentDropsNumber = len(stats.currentDropsList)
                        initDropsNumber = len(stats.initDropsList)
                        sessionDropsNumber = currentDropsNumber - initDropsNumber
                        todayDrops = stats.todayDrops
                        sessionWatchHour = round(float(stats.currentWatchHour) - float(stats.initWatchHour), 2)
                        if todayDrops == 0:
                            todayDrops = ""
                        else:
                            todayDrops = f"({todayDrops})"
                        log.info(
                            f"{_log('程序启动时间: ')}"
                            f"{formattedOpenDatetime} | "
                            f"{_log('运行掉落总和(今日):')}"
                            f"{sessionDropsNumber}{todayDrops} | "
                            f"{_log('生涯总掉落:')}"
                            f"{initDropsNumber}+{sessionDropsNumber} | "
                            f"{_log('总观看时长: ')}"
                            f"{stats.initWatchHour}+{sessionWatchHour}")
                        if len(stats.sessionDropsDict) != 0:
                            log.info(
                                f"{_log('本次运行掉落详细:')} "
                                f"{stats.sessionDropsDict}")
                    elif stats.currentDropsList == [" "]:
                        try:
                            log.error(_log("统计掉落数出错,掉落数小于0"))
                            if not any(_("统计掉落数出错,掉落数小于0", color="red") in info for info in stats.info):
                                stats.info.append(f"{datetime.now().strftime('%H:%M:%S')} " + _("统计掉落数出错,掉落数小于0", color="red"))
                        except Exception:
                            pass
                # Make sure to come to the lolesports schedule page
                try:
                    getLolesportsWeb(self.driver)
                except Exception:
                    debugScreen(self.driver, "lolesports")
                    log.error(formatExc(format_exc()))
                    log.error(_log("无法打开Lolesports网页，网络问题，将于3秒后退出..."))
                    errorNotify(error=_log("无法打开Lolesports网页，网络问题，将于3秒后退出..."))
                    stats.info.append(f"{datetime.now().strftime('%H:%M:%S')} " + _("无法打开Lolesports网页，网络问题，将于3秒后退出...", color="red"))
                    sysQuit(self.driver, _log("无法打开Lolesports网页，网络问题，将于3秒后退出..."))

                # matches = self.getMatchInfo()
                liveList = fetchLiveMatches(ignoreBroadCast=config.ignoreBroadCast)
                if liveList == ["ERROR"]:
                    liveUrlList = self.getMatchInfo()
                    tempList = []
                    for live in liveUrlList:
                        tempList.append(live.split('/')[-1])
                    liveList = tempList
                if config.onlyWatchMatches:
                    liveList = sortLiveList(liveList, config.onlyWatchMatches)
                safeModeMatches = ["worlds", "msi", "lcs", "lec", "lla", "vcs", "pcs", "lpl", "lck", "ljl-japan", "lco", "cblol-brazil", "tft_esports", "emea_masters"]
                if config.mode == "safe":
                    liveList = sortLiveList(liveList, safeModeMatches)
                liveUrlList = []
                for live in liveList:
                    liveUrlList.append("https://lolesports.com/live/" + live)
                names = updateLiveRegions(liveUrlList)
                for league in stats.liveRegions:
                    if league.name not in names:
                        stats.liveRegions.remove(league)
                sleep(2)
                matchesLen = len(liveUrlList)
                if matchesLen == 0:
                    log.info(_log("没有赛区正在直播"))
                # 1 match
                elif matchesLen == 1:
                    log.info(
                        f"{matchesLen} {_log('个赛区正在直播中')}")
                # multiple matches
                else:
                    log.info(
                        f"{matchesLen} {_log('赛区正在直播中')}")
                # Close the live streams of the regions that have already ended.
                self.closeFinishedTabs(liveMatches=liveUrlList)
                # Start watching the new live broadcast.
                try:
                    self.startWatchNewMatches(liveMatches=liveUrlList)
                except Exception:
                    log.error(_log("打开新比赛时发生错误"))
                    log.error(formatExc(format_exc()))
                    errorNotify(error=_log("打开新比赛时发生错误"))
                    stats.info.append(f"{datetime.now().strftime('%H:%M:%S')} " + _("打开新比赛时发生错误", color="red"))
                sleep(3)
                # Switch back to main page.
                self.driver.switch_to.window(self.mainWindow)
                # Check information of the most recent match.
                # self.checkNextMatch()
                if newDelay == 3599:
                    log.info(_log("识别到距离比赛时间较长 检查间隔为1小时"))
                    stats.info.append(f"{datetime.now().strftime('%H:%M:%S')} " + _("识别到距离比赛时间较长 检查间隔为1小时", color="green"))
                log.info(
                    f"{_log('下次检查在:')} "
                    f"{(datetime.now() + timedelta(seconds=newDelay)).strftime('%m-%d %H:%M:%S')}")
                log.info(f"{'=' * 50}")
                stats.nextCheckTime = "[cyan]" + (datetime.now() + timedelta(seconds=newDelay)).strftime('%H:%M:%S') + "[/]"
                stats.status = _("在线", color="bold green")
                sleep(newDelay)
            if time.time() >= endTimePoint and config.maxRunHours != -1 and config.platForm == "windows":
                log.info(_log("程序设定运行时长已到，将于60秒后关机,请及时做好准备工作"))
                stats.info.append(f"{datetime.now().strftime('%H:%M:%S')} " +
                                  _("程序设定运行时长已到，将于60秒后关机,请及时做好准备工作", color="yellow"))
                os.system("shutdown -s -t 60")

        except NoSuchWindowException:
            log.error(_log("对应窗口找不到") + "，" + _log("检查是否手动关闭或电脑运存不足"))
            stats.info.append(f"{datetime.now().strftime('%H:%M:%S')} " + _("对应窗口找不到", color="red") + "，" + _("检查是否手动关闭或电脑运存不足", color="red"))
            log.error(formatExc(format_exc()))
            errorNotify(_log("对应窗口找不到") + "，" + _log("检查是否手动关闭或电脑运存不足"))
            debugScreen(self.driver, "main")
            sysQuit(self.driver, _log("对应窗口找不到") + "，" + _log("检查是否手动关闭或电脑运存不足"))
        except Exception:
            log.error(_log("发生错误"))
            stats.info.append(f"{datetime.now().strftime('%H:%M:%S')} " + _("发生错误", color="red"))
            log.error(formatExc(format_exc()))
            errorNotify(_log("发生错误"))
            debugScreen(self.driver, "main")
            sysQuit(self.driver, _log("发生错误"))

    def getMatchInfo(self, ignoreBroadCast=True):
        """
        Function: getMatchInfo
        Description: Fetches the URLs of the live matches from the lolesports website.

        Input:
        - ignoreBroadCast: A boolean value indicating whether to ignore broadcast matches or not.

        Output:
        - matches: A list containing the URLs of the live matches.

        Exceptions:
        - If an exception occurs while fetching the URLs of the live matches, it logs the error message and returns an empty list.
        """
        try:
            matches = []
            # Make sure it is the latest page information.
            self.driver.refresh()
            sleep(2)
            trueMatchElements = self.driver.find_elements(
                by=By.CSS_SELECTOR, value=".EventMatch .event.live")
            matchElements = self.driver.find_elements(
                by=By.CSS_SELECTOR, value=".event.live")
            if config.ignoreBroadCast and ignoreBroadCast:
                for element in trueMatchElements:
                    matches.append(element.get_attribute("href"))
            else:
                for element in matchElements:
                    matches.append(element.get_attribute("href"))
            log.error(_log("WEB 获取比赛列表成功"))
            return matches
        except Exception:
            log.error("WEB " + _log("获取比赛列表失败"))
            stats.info.append(f"{datetime.now().strftime('%H:%M:%S')} " + "WEB " + _("获取比赛列表失败", color="red"))
            debugScreen(self.driver, "getMatchInfo")
            log.error(formatExc(format_exc()))
            return []

    def closeAllTabs(self):
        """
        Closes all open tabs about lolesports.
        """
        try:
            removeList = []
            newTab1 = None
            if config.countDrops:
                self.driver.switch_to.new_window('tab')
                newTab1 = self.driver.current_window_handle
                sleep(1)
            self.driver.switch_to.new_window('tab')
            newTab2 = self.driver.current_window_handle
            sleep(1)
            for keys in self.currentWindows.keys():
                self.driver.switch_to.window(self.currentWindows[keys])
                sleep(1)
                self.driver.close()
                removeList.append(keys)
                sleep(1)
            self.driver.switch_to.window(self.mainWindow)
            sleep(1)
            self.driver.close()
            self.mainWindow = newTab2
            sleep(1)
            if config.countDrops:
                self.driver.switch_to.window(self.rewardWindow)
                sleep(1)
                self.driver.close()
                self.rewardWindow = newTab1
            for handle in removeList:
                self.currentWindows.pop(handle, None)
            stats.info.append(f"{datetime.now().strftime('%H:%M:%S')} " + _("所有窗口已关闭", color="green"))
            log.info(_log("所有窗口已关闭"))
            stats.lives = []
            self.streamNumber = 0
        except Exception:
            debugScreen(self.driver, "closeAllTabs")
            log.error(_log("关闭所有窗口时发生异常"))
            stats.info.append(f"{datetime.now().strftime('%H:%M:%S')} " + _("关闭所有窗口时发生异常", color="red"))
            errorNotify(error=_log("关闭所有窗口时发生异常"))
            log.error(formatExc(format_exc()))

    def closeFinishedTabs(self, liveMatches):
        """
        Close the Ended Contests tab and update the self.currentWindows dictionary.

        Args:
            liveMatches: A list of matches in the live stream with a link to the match.

        """
        try:
            removeList = []
            for keys in self.currentWindows.keys():
                self.driver.switch_to.window(self.currentWindows[keys])
                sleep(1)
                if keys not in liveMatches:
                    match = getMatchName(keys)
                    name = formatLeagueName(match)
                    log.info(f"{name} {_log('比赛结束')}")
                    stats.info.append(f"{datetime.now().strftime('%H:%M:%S')} "
                                      + f"[bold magenta]{name}[/bold magenta] {_('比赛结束', color='green')}")
                    for live in stats.lives:
                        if live.league == match:
                            stats.lives.remove(live)
                    self.driver.close()
                    removeList.append(keys)
                    sleep(2)
                    self.driver.switch_to.window(self.mainWindow)
                    sleep(3)
                else:
                    if keys in self.OVERRIDES:
                        self.rewards.checkMatches("twitch", OVERRIDES[keys])
                    else:
                        self.rewards.checkMatches("youtube", keys)
            for keys in removeList:
                self.currentWindows.pop(keys, None)
                self.streamNumber -= 1
            self.driver.switch_to.window(self.mainWindow)
        except Exception:
            debugScreen(self.driver, "closeFinishedTabs")
            stats.info.append(f"{datetime.now().strftime('%H:%M:%S')} " + _("关闭已结束的比赛时发生错误", color="red"))
            errorNotify(error=_log("关闭已结束的比赛时发生错误"))
            log.error(formatExc(format_exc()))

    @retry(stop_max_attempt_number=2, wait_incrementing_increment=10000, wait_incrementing_start=10000)
    def startWatchNewMatches(self, liveMatches):
        """
        startWatchNewMatches method opens new browser tabs for each live match that is not already being watched,
        and skips matches that are in the disWatchMatches list.
        It then switches to the new tab and loads the stream URL, setting the quality to the desired level if possible.

        Args:
        - liveMatches (list): a list of strings representing the names or URLs of live matches.
        - disWatchMatches (list): a list of strings representing the names or keywords of matches to be skipped.

        """
        try:
            newLiveMatches = sorted(list(set(liveMatches) - set(self.currentWindows.keys())), key=lambda x: liveMatches.index(x))
            disWatchMatchesSet = set(config.disWatchMatches)
            onlyWatchMatchesSet = set(config.onlyWatchMatches)
            if config.mode == "safe":
                safeList = ["worlds", "msi", "lcs", "lec", "lla", "vcs", "pcs", "lpl", "lck", "ljl-japan", "lco", "cblol-brazil", "tft_esports", "emea_masters"]
                onlyWatchMatchesSet = set(safeList)
            elif config.mode == "normal":
                pass

            for match in newLiveMatches:
                skipName = getMatchName(match)
                if disWatchMatchesSet and any(disWatch in match for disWatch in disWatchMatchesSet):
                    log.info(f"{skipName} {_log('比赛跳过')}")
                    updateLiveRegionsColor(skipName, "dim yellow")
                    if not any(f"[bold magenta]{skipName}[/bold magenta] {_('比赛跳过', color='yellow')}" in info for info in stats.info):
                        stats.info.append(f"{datetime.now().strftime('%H:%M:%S')} " +
                                          f"[bold magenta]{skipName}[/bold magenta] {_('比赛跳过', color='yellow')}")
                    continue

                if onlyWatchMatchesSet and match.split('/')[-1] not in onlyWatchMatchesSet:
                    log.info(f"{skipName} {_log('比赛跳过')}")
                    updateLiveRegionsColor(skipName, "dim yellow")
                    if not any(f"[bold magenta]{skipName}[/bold magenta] {_('比赛跳过', color='yellow')}" in info for info in stats.info):
                        stats.info.append(f"{datetime.now().strftime('%H:%M:%S')} " +
                                          f"[bold magenta]{skipName}[/bold magenta] {_('比赛跳过', color='yellow')}")
                    continue

                if self.streamNumber >= config.maxStream:
                    log.info(_log("已达到最大观看赛区数, 剩余比赛将不予观看"))
                    name = getMatchName(match)
                    updateLiveRegionsColor(name, "dim yellow")
                    if not any(_("已达到最大观看赛区数, 剩余比赛将不予观看", color="yellow") in info for info in stats.info):
                        stats.info.append(f"{datetime.now().strftime('%H:%M:%S')} " +
                                          _("已达到最大观看赛区数, 剩余比赛将不予观看", color="yellow"))
                    for league in stats.liveRegions:
                        if "white" == league.color:
                            league.color = "dim yellow"

                    break
                self.driver.switch_to.new_window('tab')
                sleep(1)
                self.currentWindows[match] = self.driver.current_window_handle
                # Identified as a Twitch stream.
                if match in self.OVERRIDES:
                    url = self.OVERRIDES[match]
                    name = getMatchName(match)
                    formatName = formatLeagueName(name)
                    self.driver.get(url)
                    updateLiveDefinition(name, "Auto")
                    log.info("Twitch " + self.driver.current_url)
                    if not self.rewards.checkMatches("twitch", url):
                        return
                    if config.closeStream:
                        if self.closeStreamElement():
                            log.info(formatName + " " + _log("视频流关闭成功."))
                            stats.info.append(f"{datetime.now().strftime('%H:%M:%S')} [bold magenta]" + formatName + "[/bold magenta] " +
                                              _("视频流关闭成功", color="green"))
                            updateLiveDefinition(name, "None")
                        else:
                            log.info(formatName + " " + _log("关闭视频流失败."))
                            stats.info.append(f"{datetime.now().strftime('%H:%M:%S')} [bold magenta]" + formatName + "[/bold magenta] " +
                                              _("关闭视频流失败", color="red"))
                    else:
                        try:
                            if self.twitch.setTwitchQuality():
                                log.info(formatName + " " + _log("Twitch 160p清晰度设置成功"))
                                updateLiveDefinition(name, "160p")
                                stats.info.append(f"{datetime.now().strftime('%H:%M:%S')} [bold magenta]" + formatName + "[/bold magenta] " +
                                                  _("Twitch 160p清晰度设置成功", color="green"))
                            else:
                                log.error(_log("Twitch 清晰度设置失败"))
                                updateLiveDefinition(name, "Auto")
                                stats.info.append(f"{datetime.now().strftime('%H:%M:%S')} [bold magenta]" + formatName + "[/bold magenta] " +
                                                  _("Twitch 清晰度设置失败", color="red"))
                        except Exception:
                            log.error(_log("无法设置 Twitch 清晰度."))
                            updateLiveDefinition(name, "Auto")
                            stats.info.append(f"{datetime.now().strftime('%H:%M:%S')} [bold magenta]" + formatName + "[/bold magenta] " +
                                              _("无法设置 Twitch 清晰度.", color="red"))
                            log.error(formatExc(format_exc()))
                # Identified as a YouTube stream.
                else:
                    url = match
                    self.driver.get(url)
                    name = getMatchName(match)
                    formatName = formatLeagueName(name)
                    updateLiveDefinition(name, "Auto")
                    # It is convenient to add to overrides next time
                    log.info("YouTube " + self.driver.current_url)
                    self.youtube.checkYoutubeStream()
                    # When rewards are not currently available, no need to set the quality
                    if not self.rewards.checkMatches("youtube", url):
                        return
                    # remove the YouTube stream
                    if config.closeStream:
                        self.closeStreamElement()
                        updateLiveDefinition(name, "None")
                    else:
                        try:
                            if self.youtube.setYoutubeQuality():
                                log.info(formatName + " " + _log("Youtube 144p清晰度设置成功"))
                                updateLiveDefinition(name, "144p")
                                stats.info.append(f"{datetime.now().strftime('%H:%M:%S')} [bold magenta]" + formatName + "[/bold magenta] " +
                                                  _("Youtube 144p清晰度设置成功", color="green"))
                            else:
                                debugScreen(self.driver, "youtube")
                                updateLiveDefinition(name, "Auto")
                                log.error(_log("无法设置 Youtube 清晰度.可能是误判成youtube源,请联系作者"))
                                stats.info.append(f"{datetime.now().strftime('%H:%M:%S')} [bold magenta]" + formatName + "[/bold magenta] " +
                                                  _("无法设置 Youtube 清晰度.可能是误判成youtube源,请联系作者", color="red"))
                        except Exception:
                            debugScreen(self.driver, "youtube")
                            log.error(_log("无法设置 Youtube 清晰度.可能是误判成youtube源,请联系作者"))
                            updateLiveDefinition(name, "Auto")
                            stats.info.append(f"{datetime.now().strftime('%H:%M:%S')} [bold magenta]" + formatName + "[/bold magenta] " +
                                              _("无法设置 Youtube 清晰度.可能是误判成youtube源,请联系作者", color="red"))
                            log.error(formatExc(format_exc()))
                self.streamNumber += 1
                sleep(4)
        except Exception:
            log.error(_log("打开新比赛时发生错误") + " " + _log("待重试"))
            log.error(formatExc(format_exc()))
            stats.info.append(f"{datetime.now().strftime('%H:%M:%S')} " + _("打开新比赛时发生错误", color="red") + " " + _("待重试", color="red"))

    def closeStreamElement(self):
        """
        Close the current video stream by removing the video player element from the DOM.
        """
        try:
            self.driver.execute_script("""var data=document.querySelector('#video-player').remove()""")
        except Exception:
            debugScreen(self.driver, "closeStreamElement")
            log.error(_log("关闭视频流失败."))
            log.error(formatExc(format_exc()))
            return False
        else:
            log.info(_log("视频流关闭成功."))
            return True

    def checkNextMatch(self):
        """
        Function: checkNextMatch
        Description: This function retrieves the details of the next upcoming match from the webpage and
                     compares it with the current date and time to determine if the match is still valid.
                     If the match is not valid, it will print a message indicating that the match has been filtered out.
                     If the match is valid, it will print the details of the next match.
        """
        try:
            nextMatchDayTime = self.driver.find_element(
                by=By.CSS_SELECTOR, value="div.divider.future + div.EventDate > div.date > span.monthday").text
            timeList = nextMatchDayTime.split(" ")
            getNextMatchRetryTimes = 4
            while len(timeList) != 2 and getNextMatchRetryTimes > 0:
                getNextMatchRetryTimes -= 1
                debugScreen(self.driver, "nextMatch")
                self.driver.refresh()
                sleep(5)
                nextMatchDayTime = self.driver.find_element(
                    by=By.CSS_SELECTOR, value="div.divider.future + div.EventDate > div.date > span.monthday").text
                timeList = nextMatchDayTime.split(" ")
            if len(timeList) != 2:
                log.error("WEB " + _log("获取下一场比赛时间失败"))
                stats.info.append(f"{datetime.now().strftime('%H:%M:%S')} WEB " + _("获取下一场比赛时间失败", color="red"))
                self.nextMatchDay = None
                return

            nextMatchMonth = timeList[0]
            nextMatchDay = int(timeList[1])
            nextMatchTime = self.driver.find_element(
                by=By.CSS_SELECTOR,
                value="div.divider.future + div.EventDate + div.EventMatch > div > div.EventTime > div > span.hour").text
            try:
                nextMatchAMOrPM = self.driver.find_element(
                    by=By.CSS_SELECTOR,
                    value="div.divider.future + div.EventDate + div.EventMatch > div > div.EventTime > div > span.hour ~ span.ampm").text
            except NoSuchElementException:
                nextMatchAMOrPM = ""
            nextMatchLeague = self.driver.find_element(
                by=By.CSS_SELECTOR,
                value="div.divider.future + div.EventDate + div.EventMatch > div > div.league > div.name").text
            nextMatchBO = self.driver.find_element(
                by=By.CSS_SELECTOR,
                value="div.divider.future + div.EventDate + div.EventMatch > div > div.league > div.strategy").text
            if nextMatchAMOrPM == "PM" and nextMatchTime != "12":
                nextMatchStartHour = int(nextMatchTime) + 12
            elif nextMatchAMOrPM == "AM" and nextMatchTime == "12":
                nextMatchStartHour = 0
            else:
                nextMatchStartHour = int(nextMatchTime)
            self.nextMatchHour = nextMatchStartHour
            self.nextMatchDay = nextMatchDay
            invalidMatch = nextMatchLeague
            nowHour = int(time.localtime().tm_hour)
            nowMonth = time.strftime("%b", time.localtime())
            nowDay = int(time.strftime("%d", time.localtime()))
            month = mouthTrans(nextMatchDayTime.split(" ")[0])
            day = nextMatchDayTime.split(" ")[1]
            if (nowMonth in nextMatchMonth and nowDay == nextMatchDay and nowHour > nextMatchStartHour) or \
                    (nowMonth not in nextMatchMonth and nowDay < nextMatchDay) or \
                    (nowMonth in nextMatchMonth and nowDay > nextMatchDay):
                nextMatchTime = self.driver.find_element(
                    by=By.CSS_SELECTOR,
                    value="div.divider.future + div.EventDate + div.EventMatch ~ div.EventMatch > div > div.EventTime > div > span.hour").text
                nextMatchAMOrPM = self.driver.find_element(
                    by=By.CSS_SELECTOR,
                    value="div.divider.future + div.EventDate + div.EventMatch ~ div.EventMatch > div > div.EventTime > div > span.hour ~ span.ampm").text
                nextMatchLeague = self.driver.find_element(
                    by=By.CSS_SELECTOR,
                    value="div.divider.future + div.EventDate + div.EventMatch ~ div.EventMatch > div > div.league > div.name").text
                nextMatchBO = self.driver.find_element(
                    by=By.CSS_SELECTOR,
                    value="div.divider.future + div.EventDate + div.EventMatch ~ div.EventMatch > div > div.league > div.strategy").text

                if nextMatchTime == "" or nextMatchLeague == "":
                    nextMatchTime = self.driver.find_element(
                        by=By.CSS_SELECTOR,
                        value="div.single.future.event > div.EventTime > div > span.hour").text
                    nextMatchAMOrPM = self.driver.find_element(
                        by=By.CSS_SELECTOR,
                        value="div.single.future.event > div.EventTime > div > span.hour ~ span.ampm").text
                    nextMatchLeague = self.driver.find_element(
                        by=By.CSS_SELECTOR,
                        value="div.single.future.event > div.league > div.name").text
                    nextMatchBO = self.driver.find_element(
                        by=By.CSS_SELECTOR,
                        value="div.single.future.event > div.league > div.strategy").text
                stats.nextMatch = f"{nextMatchLeague}|" \
                                  f"{timeTrans(nextMatchTime + nextMatchAMOrPM)}"

                self.nextMatchDay = None
            else:
                stats.nextMatch = f"{nextMatchLeague}|" \
                                  f"{month}{day} " \
                                  f"{timeTrans(nextMatchTime + nextMatchAMOrPM)}"
            log.info(_log("WEB 获取下一场比赛时间成功"))
        except Exception:
            debugScreen(self.driver, "nextMatch")
            log.error("WEB " + _log("获取下一场比赛时间失败"))
            log.error(formatExc(format_exc()))
            stats.info.append(f"{datetime.now().strftime('%H:%M:%S')} WEB {_('获取下一场比赛时间失败', color='red')}")
