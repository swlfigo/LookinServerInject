//
//  EntryPointFile.m
//  LookinInject
//
//  Created by sylar on 2025/2/6.
//

#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import "LKS_ConnectionManager.h"
static void __attribute__((constructor)) entryPointTest(void){
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(10 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
        UIWindow *window = [UIApplication sharedApplication].keyWindow;
        UIAlertController *alertC = [UIAlertController alertControllerWithTitle:@"Bravo🎉" message:@"🍺 Injection LookinServer Success!" preferredStyle:nil];
        [alertC addAction:[UIAlertAction actionWithTitle:@"OK" style:UIAlertActionStyleDefault handler:nil]];
        [[window rootViewController] presentViewController:alertC animated:YES completion:nil];
        [LKS_ConnectionManager sharedInstance];
    });
}
