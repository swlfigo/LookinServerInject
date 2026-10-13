//
//  EntryPointFile.m
//  LookinInject
//
//  Created by sylar on 2025/2/6.
//

#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import "LKS_ConnectionManager.h"

#ifdef SHOULD_COMPILE_LOOKIN_SERVER

#ifndef LOOKIN_INJECT_SHOW_NOTICE
#define LOOKIN_INJECT_SHOW_NOTICE 1
#endif

#if LOOKIN_INJECT_SHOW_NOTICE
@interface LookinInjectionNotice : NSObject
@property(nonatomic, assign) BOOL hasShownNotice;
+ (instancetype)sharedInstance;
- (void)showIfReady;
@end

@implementation LookinInjectionNotice

+ (instancetype)sharedInstance {
    static LookinInjectionNotice *instance;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        instance = [[self alloc] init];
    });
    return instance;
}

- (instancetype)init {
    if ((self = [super init])) {
        NSNotificationCenter *center = [NSNotificationCenter defaultCenter];
        for (NSString *name in @[LKS_ServerDidBecomeReadyNotificationName,
                                 UIApplicationDidBecomeActiveNotification,
                                 UISceneDidActivateNotification,
                                 UIWindowDidBecomeKeyNotification,
                                 UIWindowDidBecomeVisibleNotification]) {
            [center addObserver:self selector:@selector(handleReadyEvent:) name:name object:nil];
        }
    }
    return self;
}

- (void)handleReadyEvent:(NSNotification *)notification {
    dispatch_async(dispatch_get_main_queue(), ^{
        [self showIfReady];
    });
}

- (UIWindow *)foregroundWindow {
    UIApplication *application = [UIApplication sharedApplication];
    UIWindow *fallback = nil;
    if (@available(iOS 13.0, *)) {
        for (UIScene *scene in application.connectedScenes) {
            if (![scene isKindOfClass:[UIWindowScene class]] ||
                scene.activationState != UISceneActivationStateForegroundActive) {
                continue;
            }
            for (UIWindow *window in ((UIWindowScene *)scene).windows) {
                if (window.hidden || window.alpha == 0 || window.windowLevel != UIWindowLevelNormal) continue;
                if (window.isKeyWindow) return window;
                if (!fallback) fallback = window;
            }
        }
    }
    if (fallback) return fallback;
    // Also supports apps that do not adopt UIWindowScene, including compatibility mode.
    for (UIWindow *window in application.windows) {
        if (@available(iOS 13.0, *)) {
            if (window.windowScene && window.windowScene.activationState != UISceneActivationStateForegroundActive) continue;
        }
        if (window.hidden || window.alpha == 0 || window.windowLevel != UIWindowLevelNormal) continue;
        if (window.isKeyWindow) return window;
        if (!fallback) fallback = window;
    }
    return fallback;
}

- (void)showIfReady {
    if (self.hasShownNotice ||
        [UIApplication sharedApplication].applicationState != UIApplicationStateActive ||
        ![LKS_ConnectionManager sharedInstance].serverReady) {
        return;
    }
    UIWindow *window = [self foregroundWindow];
    if (!window || CGRectIsEmpty(window.bounds)) return;
    self.hasShownNotice = YES;

    UIVisualEffectView *notice = [[UIVisualEffectView alloc] initWithEffect:
        [UIBlurEffect effectWithStyle:UIBlurEffectStyleSystemMaterial]];
    notice.translatesAutoresizingMaskIntoConstraints = NO;
    notice.userInteractionEnabled = NO;
    notice.layer.cornerRadius = 12;
    notice.clipsToBounds = YES;
    notice.alpha = 0;

    UILabel *label = [[UILabel alloc] init];
    label.translatesAutoresizingMaskIntoConstraints = NO;
    label.text = @"Lookin 已注入\n可在电脑上连接查看 UI";
    label.textColor = [UIColor labelColor];
    label.font = [UIFont preferredFontForTextStyle:UIFontTextStyleSubheadline];
    label.adjustsFontForContentSizeCategory = YES;
    label.textAlignment = NSTextAlignmentCenter;
    label.numberOfLines = 0;
    [notice.contentView addSubview:label];
    [window addSubview:notice];

    NSLayoutConstraint *preferredWidth = [notice.widthAnchor constraintEqualToAnchor:window.widthAnchor constant:-32];
    preferredWidth.priority = UILayoutPriorityDefaultHigh;
    [NSLayoutConstraint activateConstraints:@[
        [notice.centerXAnchor constraintEqualToAnchor:window.centerXAnchor],
        [notice.topAnchor constraintEqualToAnchor:window.safeAreaLayoutGuide.topAnchor constant:12],
        [notice.leadingAnchor constraintGreaterThanOrEqualToAnchor:window.leadingAnchor constant:16],
        [notice.trailingAnchor constraintLessThanOrEqualToAnchor:window.trailingAnchor constant:-16],
        [notice.widthAnchor constraintLessThanOrEqualToConstant:340],
        preferredWidth,
        [label.leadingAnchor constraintEqualToAnchor:notice.contentView.leadingAnchor constant:18],
        [label.trailingAnchor constraintEqualToAnchor:notice.contentView.trailingAnchor constant:-18],
        [label.topAnchor constraintEqualToAnchor:notice.contentView.topAnchor constant:12],
        [label.bottomAnchor constraintEqualToAnchor:notice.contentView.bottomAnchor constant:-12]
    ]];

    [UIView animateWithDuration:0.2 animations:^{ notice.alpha = 1; }];
    UIAccessibilityPostNotification(UIAccessibilityAnnouncementNotification, label.text);
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(3 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
        [UIView animateWithDuration:0.2 animations:^{ notice.alpha = 0; } completion:^(BOOL finished) {
            [notice removeFromSuperview];
        }];
    });
}

@end
#endif

static void __attribute__((constructor)) LookinInjectionEntryPoint(void) {
    dispatch_async(dispatch_get_main_queue(), ^{
#if LOOKIN_INJECT_SHOW_NOTICE
        LookinInjectionNotice *notice = [LookinInjectionNotice sharedInstance];
#endif
        // +load handles normal startup; this also handles injection into an already active app.
        [[LKS_ConnectionManager sharedInstance] startIfNeeded];
#if LOOKIN_INJECT_SHOW_NOTICE
        [notice showIfReady];
#endif
    });
}

#endif
