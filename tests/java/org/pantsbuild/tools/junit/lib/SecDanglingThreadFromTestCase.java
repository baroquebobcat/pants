package org.pantsbuild.tools.junit.lib;

import org.junit.Test;

public class SecDanglingThreadFromTestCase {
  @Test
  public void startedThread() {
    Thread thread = new Thread(new Runnable() {
      @Override
      public void run() {
        try {
          System.out.println("waiting 1 sec");
          Thread.sleep(1000);
          System.out.println("ending thread");
        } catch (InterruptedException e) {
          // ignored
          System.out.println("caught interrupt");
        }
      }
    });
    thread.start();
    System.out.println("got here");
  }
}
